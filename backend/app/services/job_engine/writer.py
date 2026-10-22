"""唯一的写入协程（02 第 5.5 节、03 第 9 节）。

任务和条目的所有写入都排进一个队列，每 300 毫秒或攒够 100 个操作提交一次事务；接口里的状态变更
（暂停、继续、取消、重试、建任务插入条目、删除）也走这里，与引擎的写入严格按顺序执行，不会互相覆盖。
每个操作可以附带一个完成通知（asyncio.Future）：事务提交后先置位这一批的完成通知，再把涉及的任务、条目
交给 EventBus 发布，保证界面看到的就是已落库的状态；任务引擎靠完成通知判断一条条目的最终状态何时真正落库。
提交失败时记录日志并逐个重试一次；仍失败则让完成通知以异常结束，并把相关任务暂停（原因码 write_failed）。

引擎的写入（标记 running、写结果、放回 pending）是“声明式”的：只给出条目和字段，由写入协程在一批里合并：
同一条目的字段按先后合并，按字段组合分组用 executemany 写入；任务计数、tokens、模型平均耗时按批汇总写一次；
跟随条目只对确实有跟随条目的主条目同步。异步驱动下每条 SQL 都要在线程和事件循环之间往返，逐条执行时
一批要几百次往返，引擎很快时写入跟不上，暂停、取消这类接口操作也要排在积压后面很久。遇到自定义操作
（接口的状态变更等）时，先把攒下的写入落下去再执行它，先后顺序不变。
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.engine import Database
from app.db.repo import items as items_repo
from app.db.repo import jobs as jobs_repo
from app.db.repo import models as models_repo
from app.services.event_bus import EventBus
from app.utils import dumps, loads

logger = logging.getLogger(__name__)

BATCH_INTERVAL = 0.3
BATCH_SIZE = 100
COLOR_SLOTS = 11

Apply = Callable[[AsyncSession, "ResultWriter", "WriteOp"], Awaitable[Any]]


@dataclass
class ItemResult:
    """主条目结束（op_item_result）：除了条目字段，还要同步跟随条目、累加任务计数和 tokens、分配类别颜色、
    更新模型平均耗时。"""

    status: str
    values: dict[str, Any]
    label: str | None
    prompt_tokens: int
    completion_tokens: int
    model_id: int | None
    model_latency_ms: int | None


@dataclass
class WriteOp:
    apply: Apply | None = None            # 自定义操作；为 None 时是声明式的条目写入（target_item、item_values、result）
    job_id: int | None = None
    item_ids: list[int] = field(default_factory=list)
    status_changed: bool = False
    job_event: str | None = None          # None：job.changed；"created"、"deleted"；"items"：只发条目事件；"none"：都不发
    urgent: bool = False                  # 接口在等结果：立即提交
    future: asyncio.Future[Any] | None = None   # 完成通知：提交后置位（值为 apply 的返回值），写入失败时以异常结束
    engine: bool = False                  # 引擎写入：失败时暂停对应任务
    target_item: int | None = None        # 声明式：写哪一条
    item_values: dict[str, Any] | None = None   # 声明式：要写的字段
    result: ItemResult | None = None      # 声明式：主条目结束时的统计


class _Staged:
    """一批里还没写入的声明式操作：同一条目的字段按先后合并。"""

    def __init__(self) -> None:
        self.values: dict[int, dict[str, Any]] = {}
        self.results: list[WriteOp] = []

    def add(self, op: WriteOp) -> None:
        if op.target_item is None:
            raise ValueError("声明式写入缺少 target_item")
        self.values.setdefault(op.target_item, {}).update(op.item_values or {})
        if op.result is not None:
            self.results.append(op)

    def clear(self) -> None:
        self.values = {}
        self.results = []

    def __bool__(self) -> bool:
        return bool(self.values or self.results)


class ResultWriter:
    def __init__(self, db: Database, bus: EventBus) -> None:
        self.db = db
        self.bus = bus
        self.queue: asyncio.Queue[WriteOp] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._colors: dict[int, dict[str, int]] = {}
        self.on_write_failed: Callable[[set[int]], None] | None = None

    # ---- 生命周期 ----

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="wenshu-writer")

    async def stop(self) -> None:
        await self.flush()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ---- 提交接口 ----

    def submit(self, op: WriteOp) -> None:
        self.queue.put_nowait(op)

    def submit_notified(self, op: WriteOp) -> asyncio.Future[Any]:
        """引擎用：照常按批提交，返回这个操作的完成通知（03 第 9 节）。"""
        op.future = asyncio.get_running_loop().create_future()
        self.submit(op)
        return op.future

    async def run(
        self,
        apply: Apply,
        *,
        job_id: int | None = None,
        item_ids: list[int] | None = None,
        status_changed: bool = False,
        job_event: str | None = None,
    ) -> Any:
        """接口调用：排进队列、立即提交，并等待 apply 的返回值（apply 抛出的 AppError 原样抛给调用方）。"""
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.submit(
            WriteOp(
                apply=apply,
                job_id=job_id,
                item_ids=list(item_ids or []),
                status_changed=status_changed,
                job_event=job_event,
                urgent=True,
                future=future,
            )
        )
        return await future

    async def flush(self) -> None:
        """等待此刻之前排队的全部操作提交完成。"""
        if self._task is None or self._task.done():
            return

        async def noop(_session: AsyncSession, _writer: ResultWriter, _op: WriteOp) -> None:
            return None

        await self.run(noop, job_event="none")

    # ---- 内部 ----

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            op = await self.queue.get()
            batch = [op]
            deadline = loop.time() + BATCH_INTERVAL
            while len(batch) < BATCH_SIZE and not any(o.urgent for o in batch):
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.queue.get(), remaining))
                except TimeoutError:
                    break
            while len(batch) < BATCH_SIZE and not self.queue.empty():
                batch.append(self.queue.get_nowait())
            try:
                await self._commit(batch)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 写入协程不能退出
                logger.exception("写入协程出现未预期的错误")

    async def _apply_batch(self, batch: list[WriteOp]) -> list[Any]:
        """一个事务：声明式写入先攒着，遇到自定义操作、或到了批次末尾时一次写入，再执行自定义操作。"""
        results: list[Any] = []
        staged = _Staged()
        async with self.db.session() as session, session.begin():
            for op in batch:
                if op.apply is None:
                    staged.add(op)
                    results.append(None)
                    continue
                if staged:
                    await self._flush_staged(session, staged)
                results.append(await op.apply(session, self, op))
            if staged:
                await self._flush_staged(session, staged)
        return results

    async def _flush_staged(self, session: AsyncSession, staged: _Staged) -> None:
        await items_repo.update_items(session, staged.values)
        if staged.results:
            await self._apply_results(session, staged.results)
        staged.clear()

    async def _apply_results(self, session: AsyncSession, ops: list[WriteOp]) -> None:
        """主条目结束：同步跟随条目，任务计数、tokens 和模型平均耗时按批汇总写一次，分配类别颜色。"""
        leaders = [op.target_item for op in ops if op.target_item is not None]
        with_followers = await items_repo.leaders_with_followers(session, leaders)
        deltas: dict[int, list[int]] = {}          # 任务 → [成功, 失败, 输入 tokens, 输出 tokens]
        latencies: dict[int, list[int]] = {}       # 模型 → 按先后的耗时
        for op in ops:
            result = op.result
            item_id = op.target_item
            if result is None or item_id is None or op.job_id is None:
                continue
            succeeded = 1 if result.status == "succeeded" else 0
            failed = 1 if result.status == "failed" else 0
            if item_id in with_followers:
                before = await items_repo.sync_followers(session, item_id, result.values)
                if before:
                    followers = sum(before.values())
                    succeeded -= before.get("succeeded", 0)
                    failed -= before.get("failed", 0)
                    if result.status == "succeeded":
                        succeeded += followers
                    elif result.status == "failed":
                        failed += followers
                    op.item_ids.extend(await items_repo.follower_ids(session, item_id))
            delta = deltas.setdefault(op.job_id, [0, 0, 0, 0])
            delta[0] += succeeded
            delta[1] += failed
            delta[2] += result.prompt_tokens
            delta[3] += result.completion_tokens
            if result.label and result.status == "succeeded":
                await self.ensure_color(session, op.job_id, result.label)
            if result.model_id is not None and result.model_latency_ms is not None:
                latencies.setdefault(result.model_id, []).append(result.model_latency_ms)
        for job_id, (succeeded, failed, prompt_tokens, completion_tokens) in deltas.items():
            await jobs_repo.add_delta(
                session,
                job_id,
                succeeded=succeeded,
                failed=failed,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        for model_id, values in latencies.items():
            await models_repo.update_avg_latency(session, model_id, values)

    async def _commit(self, batch: list[WriteOp]) -> None:
        backup = copy.deepcopy(self._colors)
        try:
            results = await self._apply_batch(batch)
        except Exception as exc:  # noqa: BLE001
            self._colors = backup
            if not isinstance(exc, AppError):
                logger.warning("批量写入失败，逐条重试：%s", exc)
            await self._commit_one_by_one(batch)
            return
        for op, result in zip(batch, results, strict=True):
            if op.future is not None and not op.future.done():
                op.future.set_result(result)
        self._publish(batch)

    async def _commit_one_by_one(self, batch: list[WriteOp]) -> None:
        done: list[WriteOp] = []
        failed_jobs: set[int] = set()
        for op in batch:
            backup = copy.deepcopy(self._colors)
            try:
                (result,) = await self._apply_batch([op])
            except Exception as exc:  # noqa: BLE001
                self._colors = backup
                if op.future is not None and not op.future.done():
                    op.future.set_exception(exc)
                if not isinstance(exc, AppError):
                    logger.error("写入失败（任务 %s）", op.job_id, exc_info=exc)
                    if op.engine and op.job_id is not None:
                        failed_jobs.add(op.job_id)
                continue
            if op.future is not None and not op.future.done():
                op.future.set_result(result)
            done.append(op)
        self._publish(done)
        if failed_jobs and self.on_write_failed is not None:
            self.on_write_failed(failed_jobs)

    def _publish(self, batch: list[WriteOp]) -> None:
        changed: dict[int, bool] = {}
        items: dict[int, list[int]] = {}
        for op in batch:
            if op.job_id is None or op.job_event == "none":
                continue
            if op.job_event == "created":
                self.bus.job_created(op.job_id)
            elif op.job_event == "deleted":
                self.bus.job_deleted(op.job_id)
                self._colors.pop(op.job_id, None)
                changed.pop(op.job_id, None)
                items.pop(op.job_id, None)
                continue
            elif op.job_event != "items":
                changed[op.job_id] = changed.get(op.job_id, False) or op.status_changed
            if op.item_ids:
                items.setdefault(op.job_id, []).extend(op.item_ids)
        for job_id, status_changed in changed.items():
            self.bus.job_changed(job_id, status_changed=status_changed)
        for job_id, ids in items.items():
            self.bus.items_changed(job_id, list(dict.fromkeys(ids)))

    # ---- 类别颜色（03 第 4.6 节）：在写入协程里按提交顺序分配，保证顺序一致 ----

    async def ensure_color(self, session: AsyncSession, job_id: int, label: str) -> None:
        colors = self._colors.get(job_id)
        if colors is None:
            row = await jobs_repo.get(session, job_id)
            if row is None:
                return
            colors = {str(k): int(v) for k, v in (loads(row.category_colors_json, {}) or {}).items()}
            self._colors[job_id] = colors
        if label in colors:
            return
        colors[label] = len(colors) if len(colors) < COLOR_SLOTS else -1
        await jobs_repo.update_fields(session, job_id, category_colors_json=dumps(colors))

    def forget_job(self, job_id: int) -> None:
        self._colors.pop(job_id, None)

    def forget_all(self) -> None:
        self._colors.clear()


# ---- 引擎使用的操作（声明式，见模块说明） ----


def op_item_values(job_id: int, item_id: int, values: dict[str, Any], *, job_event: str | None = None) -> WriteOp:
    """不影响计数的条目字段变化：标记 running（job_event="items"，只发条目事件）、回到 pending 等。"""
    return WriteOp(
        job_id=job_id, item_ids=[item_id], engine=True, job_event=job_event, target_item=item_id, item_values=values
    )


def op_item_result(
    job_id: int,
    item_id: int,
    values: dict[str, Any],
    *,
    label: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    model_id: int | None,
    model_latency_ms: int | None,
) -> WriteOp:
    """主条目结束：写条目、同步跟随条目、任务计数和 tokens、类别颜色、模型平均耗时，在同一个事务里。"""
    return WriteOp(
        job_id=job_id,
        item_ids=[item_id],
        engine=True,
        target_item=item_id,
        item_values=values,
        result=ItemResult(
            status=str(values["status"]),
            values=values,
            label=label,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_id=model_id,
            model_latency_ms=model_latency_ms,
        ),
    )
