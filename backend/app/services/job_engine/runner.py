"""JobRunner（执行器）：每个运行中（或暂停后还在收尾）的任务一个，跑在一个 asyncio 任务里（02 第 5.2 节）。

- 键集分页：按 seq > cursor 每次取 500 条待处理的主条目，扫到底再从头扫一遍，捡回运行中被单条重跑的条目；
- in_flight：从派发开始，到这条的最终状态被写入协程提交为止（完成通知置位），查询时排除它们，
  避免写入协程提交前（最长 300 毫秒）仍是 pending 的条目被重复派发；
- _process 不抛异常（只让 CancelledError 继续抛出）：TaskGroup 里任一子任务抛异常都会连带取消其他子任务；
  需要暂停整个任务时调用 request_stop("pause", 原因码, 原因)；
- 任务级名额在处理结束时释放，不等落库；完成通知置位后才移出 in_flight 并唤醒主循环；
- 背压：in_flight 达到 MAX_UNCOMMITTED（已派发、结果还没落库）时暂停派发。模型很快时引擎可能比写入协程快，
  不设上限的话写入队列越积越长，暂停、取消这类接口操作要排在积压后面很久才能生效。
"""

from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobItemRow
from app.db.repo import items as items_repo
from app.db.repo import jobs as jobs_repo
from app.services.job_engine import reasons
from app.services.job_engine.limiter import ResizableLimiter
from app.services.job_engine.processor import ItemOutcome, ItemProcessor
from app.services.job_engine.progress import ProgressTracker
from app.services.job_engine.writer import ResultWriter, WriteOp, op_item_result, op_item_values
from app.services.llm_client import CIRCUIT_CODES
from app.utils import dumps, now_iso

if TYPE_CHECKING:
    from app.services.job_engine.manager import JobManager

logger = logging.getLogger(__name__)

PAGE_SIZE = 500
STUCK_ROUNDS = 3
MAX_UNCOMMITTED = 200      # 每个执行器已派发、结果还没落库的条目上限（约两批写入）


def leader_values(row: JobItemRow) -> dict[str, Any]:
    return {name: getattr(row, name) for name in items_repo.FOLLOWER_FIELDS}


@dataclass
class _Dispatch:
    """一次派发：子任务开始执行后 started 置为 True（见 JobRunner._task_done）。"""

    started: bool = False


class JobRunner:
    def __init__(self, manager: JobManager, job_id: int, concurrency: int, processor: ItemProcessor,
                 model_id: int | None, *, tracker: ProgressTracker) -> None:
        self.manager = manager
        self.job_id = job_id
        self.job_slots = ResizableLimiter(concurrency)
        self.tracker = tracker
        self.processor = processor
        self.model_id = model_id
        self.stop_requested: str | None = None      # None | "pause" | "cancel"
        self.cursor = 0
        self.in_flight: set[int] = set()
        self.exiting = False                        # 主循环已结束：不能再复用，“继续”时新建执行器
        self.consecutive_failures = 0
        self.task: asyncio.Task[None] | None = None
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._wake = asyncio.Event()
        self._dispatched = 0

    @property
    def writer(self) -> ResultWriter:
        return self.manager.writer

    @property
    def active(self) -> bool:
        """还在派发新条目（没有停止请求、主循环没结束）。"""
        return not self.exiting and self.stop_requested is None

    # ---- 控制 ----

    def wake(self) -> None:
        self._wake.set()

    def request_stop(self, kind: str, code: str | None = None, reason: str = "", *, write: bool = True,
                     engine: bool = True) -> None:
        """kind 为 "pause" 或 "cancel"。暂停时 write=True 由执行器写任务状态（只在仍是 queued、running 时）；
        接口发起的暂停、取消已经自己写好状态，传 write=False。"""
        if self.stop_requested == "cancel":
            return
        first = self.stop_requested is None
        self.stop_requested = kind
        if kind == "cancel":
            for task in list(self._tasks.values()):
                task.cancel()
        elif write and first and code is not None:
            logger.info("任务 %d 自动暂停（%s）：%s", self.job_id, code, reason)
            self.writer.submit(self.manager.pause_op(self.job_id, code, reason, engine=engine))
        self.manager.update_running_count()
        self.wake()

    def resume(self, processor: ItemProcessor, model_id: int | None, concurrency: int) -> None:
        """02 第 5.4 节：暂停后还在收尾时复用这个执行器——清除停止请求、换成当前的模型配置并唤醒主循环。"""
        self.processor = processor
        self.model_id = model_id
        if self.job_slots.capacity != concurrency:
            self.job_slots.resize(concurrency)
        self.stop_requested = None
        self.consecutive_failures = 0
        self.wake()

    def cancel_in_flight(self) -> None:
        """程序退出时等待超时：取消剩余的条目（放回 pending，不计失败）。"""
        for task in list(self._tasks.values()):
            task.cancel()

    async def _wait_wake(self) -> None:
        await self._wake.wait()
        self._wake.clear()

    # ---- 主循环 ----

    async def run(self) -> None:
        idle_rounds = 0
        try:
            while True:
                self._dispatched = 0
                async with asyncio.TaskGroup() as group:
                    await self._loop(group)
                if await self._finish():
                    break
                # 收尾时发现还有待处理的条目（例如刚被单条重跑）：从头再扫一遍
                idle_rounds = 0 if self._dispatched else idle_rounds + 1
                if idle_rounds >= STUCK_ROUNDS:
                    logger.error("任务 %d 有待处理的条目但无法派发，已暂停", self.job_id)
                    self.request_stop("pause", reasons.WRITE_FAILED, "有条目无法继续处理，详情见日志")
                    break
                self.exiting = False
                self.cursor = 0
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 执行器自身出错时暂停任务，不让异常丢失
            logger.exception("任务 %d 的执行器出错", self.job_id)
            self.request_stop("pause", reasons.WRITE_FAILED, "内部错误，详情见日志")
        finally:
            self.exiting = True
            self.manager.runner_exited(self)

    async def _page(self) -> list[JobItemRow]:
        async with self.manager.db.session() as session:
            return await items_repo.pending_leaders(
                session, self.job_id, after_seq=self.cursor, exclude_ids=self.in_flight, limit=PAGE_SIZE
            )

    async def _loop(self, group: asyncio.TaskGroup) -> None:
        """返回前同步置 exiting：之后“继续”不再复用这个执行器（它不会再派发），由 JobManager 新建。"""
        while True:
            if self.stop_requested:                     # 暂停或取消：不再派发，等进行中的条目收尾
                if not self.in_flight:
                    self.exiting = True
                    return
                await self._wait_wake()                 # 条目落库、或“继续”清除了停止请求时被唤醒
                continue
            batch = await self._page()
            if not batch:
                if self.cursor > 0:                     # 扫到底了，从头再扫一遍
                    self.cursor = 0
                    continue
                if not self.in_flight:                  # 从头扫也没有，进行中的也都落库了：全部完成
                    self.exiting = True
                    return
                await self._wait_wake()
                continue
            for item in batch:
                # 背压：已派发但结果还没落库的条目达到上限时，先等写入协程赶上来再派发
                while len(self.in_flight) >= MAX_UNCOMMITTED and not self.stop_requested:
                    await self._wait_wake()
                if self.stop_requested:
                    break
                await self.job_slots.acquire()
                if self.stop_requested:
                    self.job_slots.release()
                    break
                self.cursor = item.seq
                self.in_flight.add(item.id)
                self._dispatched += 1
                dispatch = _Dispatch()
                task = group.create_task(self._process(item, self.processor, dispatch), name=f"wenshu-item-{item.id}")
                task.add_done_callback(functools.partial(self._task_done, item.id, dispatch))
                self._tasks[item.id] = task

    # ---- 一条条目 ----

    async def _process(self, item: JobItemRow, processor: ItemProcessor, dispatch: _Dispatch) -> None:
        """不抛异常：内部捕获全部异常，只让 CancelledError 继续抛出（被取消的子任务不会连带取消其他子任务）。"""
        job_id, item_id = self.job_id, item.id
        dispatch.started = True
        notice: asyncio.Future[Any] | None = None
        try:
            outcome = await self._run_item(item, processor)
            notice = self._record(item, outcome)
        except asyncio.CancelledError:
            # 取消任务、程序退出打断：先把“放回 pending”交给写入协程，再直接移出 in_flight，不等完成通知
            self.writer.submit(op_item_values(job_id, item_id, {"status": "pending", "started_at": None}))
            self._settle(item_id, completed=False)
            self._leave(item_id)
            raise
        except Exception:  # noqa: BLE001 - 兜底：这一条留在 running，收尾时（_finish）放回 pending
            logger.exception("任务 %d 第 %d 行的结果没能交给写入协程", job_id, item.row_number)
        self._settle(item_id, completed=notice is not None)
        if notice is not None:
            try:
                await notice
            except asyncio.CancelledError:
                self._leave(item_id)          # 结果已经交给写入协程，不再放回 pending
                raise
            except Exception:  # noqa: BLE001 - 写入失败：任务已因 write_failed 暂停
                logger.warning("任务 %d 第 %d 行的结果没有保存", job_id, item.row_number)
        self._leave(item_id)

    async def _run_item(self, item: JobItemRow, processor: ItemProcessor) -> ItemOutcome:
        """标记 running（写 started_at 和 render_meta_json）、加入处理中集合，再交给处理器。意外异常记为 INTERNAL_ERROR。"""
        try:
            meta = processor.render_meta(item)
            self.tracker.start(item.id, item.seq, item.row_number, item.input_text, int(item.attempts or 0) + 1)
            self.writer.submit(op_item_values(
                self.job_id, item.id,
                {"status": "running", "started_at": now_iso(), "render_meta_json": dumps(meta)},
                job_event="items",
            ))
            self.manager.bus.tracks_changed(self.job_id)
            return await processor.process(item, meta)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 一条出意外不影响其他条目
            logger.exception("处理第 %d 行时出现未预期的错误", item.row_number)
            return processor.internal_error(item, exc)

    def _task_done(self, item_id: int, dispatch: _Dispatch, _task: asyncio.Task[None]) -> None:
        """子任务结束的回调。还没开始执行就被取消的子任务不会执行 _process 的任何代码：在这里归还名额、
        移出 in_flight（条目在库里仍是 pending，不用写），否则主循环会一直等它。"""
        if dispatch.started:
            return
        self.job_slots.release()
        self._leave(item_id)

    def _settle(self, item_id: int, *, completed: bool) -> None:
        """处理结束：移出处理中集合、释放任务级名额（不等落库）、推送轨道更新。"""
        self.tracker.finish(item_id, completed=completed)
        self.job_slots.release()
        self.manager.bus.tracks_changed(self.job_id)

    def _leave(self, item_id: int) -> None:
        self._tasks.pop(item_id, None)
        self.in_flight.discard(item_id)
        self.wake()

    def _record(self, item: JobItemRow, outcome: ItemOutcome) -> asyncio.Future[Any]:
        if outcome.status == "pause":
            # 鉴权失败、模型不存在：这一条放回 pending（不计失败），任务暂停
            notice = self.writer.submit_notified(op_item_values(self.job_id, item.id, outcome.values))
            self.request_stop("pause", outcome.pause_code, outcome.pause_reason or "")
            return notice
        notice = self.writer.submit_notified(
            op_item_result(
                self.job_id,
                item.id,
                outcome.values,
                label=outcome.label,
                prompt_tokens=outcome.prompt_tokens,
                completion_tokens=outcome.completion_tokens,
                model_id=self.model_id,
                model_latency_ms=outcome.model_latency_ms,
            )
        )
        if outcome.status == "succeeded":
            self.consecutive_failures = 0
        elif outcome.error_code in CIRCUIT_CODES:
            # 05 第 6.3 节：连续 10 条以超时、连不上、服务端错误最终失败时暂停；这些条目保持 failed
            self.consecutive_failures += 1
            if self.consecutive_failures >= reasons.CIRCUIT_THRESHOLD:
                self.request_stop("pause", reasons.CIRCUIT_BREAKER, reasons.circuit_breaker_text(outcome.error_message))
        return notice

    # ---- 收尾 ----

    async def _finish(self) -> bool:
        """只在没有停止请求时把任务置为 completed（按真实数据重算计数）。返回 False 表示还有待处理的条目。"""
        if self.stop_requested:
            return True
        job_id = self.job_id

        async def apply(session: AsyncSession, _writer: ResultWriter, _op: WriteOp) -> bool:
            for leader in await items_repo.orphan_follower_leaders(session, job_id):
                await items_repo.sync_followers(session, leader.id, leader_values(leader))
            # 这时执行器没有进行中的条目：仍标着 running 的（例如结果写入失败）放回 pending 重新处理
            if await items_repo.reset_running(session, job_id):
                return False
            if await jobs_repo.has_pending_items(session, job_id):
                return False
            await jobs_repo.recount(session, job_id)
            row = await jobs_repo.get(session, job_id)
            if row is None or row.status != "running":
                return True
            await jobs_repo.update_fields(session, job_id, status="completed", status_reason="",
                                          status_reason_code=None, finished_at=now_iso())
            return True

        try:
            return bool(await self.writer.run(apply, job_id=job_id, status_changed=True))
        except Exception:  # noqa: BLE001
            logger.exception("任务 %d 收尾失败", job_id)
            return True
