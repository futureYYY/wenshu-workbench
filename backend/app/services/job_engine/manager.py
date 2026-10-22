"""JobManager：全局唯一，每个任务最多持有一个 JobRunner；提供开始、暂停、继续、取消、重试失败项、单条重跑；
程序退出时暂停全部（02 第 5.1、5.4、5.7 节；03 第 6 节状态机）。

状态变更都通过写入协程执行，在事务里先检查当前状态再写，与引擎自身的写入严格排序。
暂停后执行器还在收尾时，“继续”复用它（清除停止请求并唤醒），不新建，否则两个执行器的任务级闸门叠加会超出任务并发。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import conflict, not_found, unprocessable
from app.config import AppConfig
from app.db.engine import Database
from app.db.models import JobRow
from app.db.repo import items as items_repo
from app.db.repo import jobs as jobs_repo
from app.db.repo import models as models_repo
from app.services.crypto import Crypto
from app.services.event_bus import EventBus
from app.services.job_engine import reasons
from app.services.job_engine.limiter import ModelLimiters
from app.services.job_engine.processor import ItemProcessor
from app.services.job_engine.progress import ProgressTracker
from app.services.job_engine.runner import JobRunner
from app.services.job_engine.writer import ResultWriter, WriteOp
from app.services.llm_client import LLMClients, ModelSpec
from app.services.model_service import row_to_spec
from app.services.prompt_render import PromptSpec
from app.utils import loads, now_iso

logger = logging.getLogger(__name__)

SHUTDOWN_GRACE_SECONDS = 3.0
STATUS_LABELS = {
    "queued": "排队中",
    "running": "运行中",
    "paused": "已暂停",
    "completed": "已完成",
    "cancelled": "已取消",
}
CLEARED_REASON: dict[str, Any] = {"status_reason": "", "status_reason_code": None}


def _state_conflict(status: str, action: str) -> Exception:
    return conflict("JOB_STATE_CONFLICT", f"任务{STATUS_LABELS.get(status, status)}，不能{action}")


@dataclass
class LaunchPlan:
    job_id: int
    concurrency: int
    model: ModelSpec
    prompt: PromptSpec
    file_name: str
    columns: list[tuple[str, str]]
    max_retries: int


class JobManager:
    def __init__(
        self, *, cfg: AppConfig, db: Database, bus: EventBus, writer: ResultWriter, llm: LLMClients, crypto: Crypto
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.bus = bus
        self.writer = writer
        self.llm = llm
        self.crypto = crypto
        self.runners: dict[int, JobRunner] = {}
        self.model_limiters = ModelLimiters()
        # 运行中任务数：只在事件循环线程里写、托盘线程只读
        self.running_count = 0
        writer.on_write_failed = self._on_write_failed

    # ---- 查询 ----

    def runtime(self, job_id: int) -> tuple[int, float | None]:
        """(进行中条数, 速度 条/分钟)。没有执行器时进行中为 0。"""
        runner = self.runners.get(job_id)
        if runner is None:
            return 0, None
        return runner.tracker.running, runner.tracker.rate_per_min()

    def tracks(self, job_id: int) -> list[dict[str, Any]]:
        runner = self.runners.get(job_id)
        return runner.tracker.snapshot() if runner is not None else []

    def tracks_version(self, job_id: int) -> int:
        runner = self.runners.get(job_id)
        return runner.tracker.version if runner is not None else 0

    def update_running_count(self) -> None:
        self.running_count = sum(1 for runner in self.runners.values() if runner.active)

    def on_model_updated(self, model_id: int, concurrency_cap: int) -> None:
        self.model_limiters.resize(model_id, concurrency_cap)

    # ---- 启动执行器 ----

    async def _prepare(self, job_id: int) -> LaunchPlan:
        """读取当前的模型配置（修好密钥后点“继续”即可生效）和任务的提示词快照。"""
        async with self.db.session() as session:
            job = await jobs_repo.get(session, job_id)
            if job is None:
                raise not_found("任务不存在")
            model_row = await models_repo.get(session, job.model_id) if job.model_id is not None else None
        if model_row is None:
            raise conflict("JOB_STATE_CONFLICT", "任务使用的模型已被删除，无法继续")
        if not model_row.enabled:
            raise unprocessable("MODEL_DISABLED", f"模型“{model_row.name}”已停用，启用后再继续")
        source = loads(job.source_json, {}) or {}
        columns = [(str(c.get("key")), str(c.get("title"))) for c in source.get("columns") or []]
        return LaunchPlan(
            job_id=job.id,
            concurrency=int(job.concurrency),
            model=row_to_spec(model_row, self.crypto),
            prompt=PromptSpec.from_mapping(loads(job.prompt_snapshot_json, {}) or {}),
            file_name=job.file_name,
            columns=columns,
            max_retries=int(job.max_retries),
        )

    def _processor(self, plan: LaunchPlan, tracker: ProgressTracker) -> ItemProcessor:
        model_id = plan.model.id if plan.model.id is not None else -1
        job_id = plan.job_id
        return ItemProcessor(
            llm=self.llm,
            model=plan.model,
            prompt=plan.prompt,
            file_name=plan.file_name,
            columns=plan.columns,
            max_retries=plan.max_retries,
            tracker=tracker,
            model_limiter=self.model_limiters.get(model_id, plan.model.concurrency_cap),
            on_track_change=lambda: self.bus.tracks_changed(job_id),
        )

    def _launch(self, plan: LaunchPlan) -> JobRunner:
        """开始处理：执行器暂停后还在收尾时复用它；否则新建。"""
        current = self.runners.get(plan.job_id)
        if current is not None and not current.exiting and current.stop_requested == "pause":
            current.resume(self._processor(plan, current.tracker), plan.model.id, plan.concurrency)
            self.update_running_count()
            return current
        if current is not None and not current.exiting and current.stop_requested is None:
            current.wake()
            return current
        tracker = ProgressTracker()
        runner = JobRunner(self, plan.job_id, plan.concurrency, self._processor(plan, tracker), plan.model.id,
                           tracker=tracker)
        self.runners[plan.job_id] = runner
        runner.task = asyncio.create_task(runner.run(), name=f"wenshu-job-{plan.job_id}")
        self.update_running_count()
        return runner

    def runner_exited(self, runner: JobRunner) -> None:
        if self.runners.get(runner.job_id) is runner:
            del self.runners[runner.job_id]
        self.update_running_count()

    def _has_live_runner(self, job_id: int) -> bool:
        """有执行器还在处理（或收尾）这个任务。"""
        runner = self.runners.get(job_id)
        return runner is not None and bool(runner.in_flight or not runner.exiting)

    # ---- 状态变更 ----

    async def _write_status(self, job_id: int, check: Any, fields: dict[str, Any], action: str) -> JobRow:
        async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> JobRow:
            row = await jobs_repo.get(session, job_id)
            if row is None:
                raise not_found("任务不存在")
            if not check(row):
                raise _state_conflict(row.status, action)
            values = dict(fields)
            if values.pop("_set_started", False) and not row.started_at:
                values["started_at"] = now_iso()
            await jobs_repo.update_fields(session, job_id, **values)
            return row

        return await self.writer.run(apply, job_id=job_id, status_changed=True)

    async def start_new(self, job_id: int) -> None:
        """建任务后立即开始：queued → running。"""
        plan = await self._prepare(job_id)
        await self._write_status(
            job_id,
            lambda row: row.status == "queued",
            {"status": "running", **CLEARED_REASON, "_set_started": True},
            "开始",
        )
        self._launch(plan)

    async def pause(self, job_id: int) -> None:
        """立即写为 paused（接口马上返回）；不再派发，进行中的条目正常处理完。"""
        await self._write_status(
            job_id,
            lambda row: row.status in ("queued", "running"),
            {"status": "paused", "status_reason": reasons.USER_PAUSE_TEXT, "status_reason_code": reasons.USER_PAUSE},
            "暂停",
        )
        runner = self.runners.get(job_id)
        if runner is not None:
            runner.request_stop("pause", reasons.USER_PAUSE, reasons.USER_PAUSE_TEXT, write=False)

    async def _start_from_paused_or_done(self, job_id: int, allowed: tuple[str, ...], action: str,
                                         requeue_failed: bool) -> int:
        """“继续”和“重试失败项”：读取当前模型配置；还有待处理条目时写为 running 并启动（或复用）执行器，
        已经没有时直接置为 completed（03 第 6.1 节 paused → completed）。返回重新排队的失败条数。"""
        async with self.db.session() as session:
            row = await jobs_repo.get(session, job_id)
        if row is None:
            raise not_found("任务不存在")
        if row.status not in allowed:
            raise _state_conflict(row.status, action)
        plan = await self._prepare(job_id)
        live_runner = self._has_live_runner(job_id)

        async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> tuple[str, int]:
            job = await jobs_repo.get(session, job_id)
            if job is None:
                raise not_found("任务不存在")
            if job.status not in allowed:
                raise _state_conflict(job.status, action)
            requeued = 0
            if requeue_failed:
                requeued = len(await items_repo.requeue_failed(session, job_id))
                if not requeued:
                    raise conflict("JOB_STATE_CONFLICT", "没有失败的条目")
            if not live_runner:
                # 没有执行器时仍标着 running 的条目（例如结果写入失败）放回 pending
                await items_repo.reset_running(session, job_id)
            await jobs_repo.recount(session, job_id)
            if not await jobs_repo.has_pending_items(session, job_id):
                await jobs_repo.update_fields(session, job_id, status="completed", **CLEARED_REASON,
                                              finished_at=now_iso())
                return "completed", requeued
            values: dict[str, Any] = {"status": "running", **CLEARED_REASON, "finished_at": None}
            if not job.started_at:
                values["started_at"] = now_iso()
            await jobs_repo.update_fields(session, job_id, **values)
            return "running", requeued

        outcome, requeued = await self.writer.run(apply, job_id=job_id, status_changed=True)
        if outcome == "running":
            self._launch(plan)
        return int(requeued)

    async def resume(self, job_id: int) -> None:
        await self._start_from_paused_or_done(job_id, ("paused",), "继续", requeue_failed=False)

    async def retry_failed(self, job_id: int) -> int:
        """仅 completed、paused 且有失败条目：失败条目置为 pending（清空错误字段），按“继续”启动。"""
        return await self._start_from_paused_or_done(job_id, ("completed", "paused"), "重试失败项",
                                                     requeue_failed=True)

    async def cancel(self, job_id: int) -> None:
        await self._write_status(
            job_id,
            lambda row: row.status in ("queued", "running", "paused"),
            {"status": "cancelled", **CLEARED_REASON, "finished_at": now_iso()},
            "取消",
        )
        runner = self.runners.get(job_id)
        if runner is not None:
            runner.request_stop("cancel")

    async def rerun_item(self, job_id: int, item_id: int) -> None:
        """单条重新处理（02 第 5.4 节）：条目正在处理时 409；否则置为 pending（跟随条目先解除 dedup_of），提交后：
        任务 completed 时按“继续”启动；running 时唤醒执行器（扫到底再从头扫时捡到这条）；paused 时只改条目。"""
        async with self.db.session() as session:
            row = await jobs_repo.get(session, job_id)
        if row is None:
            raise not_found("任务不存在")
        plan = await self._prepare(job_id) if row.status == "completed" else None

        async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> str:
            job = await jobs_repo.get(session, job_id)
            if job is None:
                raise not_found("任务不存在")
            if job.status == "cancelled":
                raise conflict("JOB_STATE_CONFLICT", "任务已取消，不能重新处理")
            item = await items_repo.get_in_job(session, job_id, item_id)
            if item is None:
                raise not_found("条目不存在")
            runner = self.runners.get(job_id)
            if item.status == "running" or (runner is not None and item_id in runner.in_flight):
                raise conflict("JOB_STATE_CONFLICT", "这一条正在处理中，处理完再重新处理")
            if item.status == "skipped":
                raise conflict("JOB_STATE_CONFLICT", "空行不需要处理")
            await items_repo.requeue_item(session, item_id, detach=item.dedup_of is not None)
            await jobs_repo.recount(session, job_id)
            if job.status == "completed":
                if plan is None:
                    raise conflict("JOB_STATE_CONFLICT", "任务状态已变化，请刷新后重试")
                await jobs_repo.update_fields(session, job_id, status="running", **CLEARED_REASON, finished_at=None)
                return "start"
            return "wake" if job.status in ("running", "queued") else "none"

        action = await self.writer.run(apply, job_id=job_id, item_ids=[item_id], status_changed=True)
        if action == "start" and plan is not None:
            self._launch(plan)
        elif action == "wake":
            current = self.runners.get(job_id)
            if current is not None and current.stop_requested is None:
                current.wake()   # 收尾中的执行器会在 _finish 里发现这条，继续处理
            else:
                # 状态是运行中却没有执行器（例如上次启动执行器失败）：补一个
                self._launch(await self._prepare(job_id))

    async def delete_job(self, job_id: int) -> None:
        async with self.db.session() as session:
            row = await jobs_repo.get(session, job_id)
        if row is None:
            raise not_found("任务不存在")
        if row.status not in ("completed", "cancelled", "paused"):
            raise conflict("JOB_STATE_CONFLICT", "运行中的任务不能删除，请先暂停或取消")
        await self._stop_runner(job_id)

        async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> None:
            job = await jobs_repo.get(session, job_id)
            if job is None:
                raise not_found("任务不存在")
            if job.status not in ("completed", "cancelled", "paused"):
                raise conflict("JOB_STATE_CONFLICT", "运行中的任务不能删除，请先暂停或取消")
            await jobs_repo.delete_job(session, job_id)

        await self.writer.run(apply, job_id=job_id, job_event="deleted")
        self.writer.forget_job(job_id)

        async def vacuum(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> None:
            await jobs_repo.incremental_vacuum(session)

        self.writer.submit(WriteOp(apply=vacuum, job_event="none"))

    async def _stop_runner(self, job_id: int, timeout: float = 5.0) -> None:
        """暂停后可能还有正在收尾的条目：取消并等执行器退出（删除任务、开发模式重置用）。"""
        runner = self.runners.get(job_id)
        if runner is None:
            return
        runner.request_stop("cancel")
        if runner.task is not None and not runner.task.done():
            await asyncio.wait([runner.task], timeout=timeout)

    # ---- 引擎触发的暂停 ----

    def pause_op(self, job_id: int, code: str, reason: str, *, engine: bool = True) -> WriteOp:
        """只在任务仍是 queued、running 时改为 paused。engine=False：这次写入失败时不再触发暂停（避免循环）。"""

        async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> bool:
            row = await jobs_repo.get(session, job_id)
            if row is None or row.status not in ("queued", "running"):
                return False
            await jobs_repo.update_fields(session, job_id, status="paused", status_reason=reason,
                                          status_reason_code=code)
            return True

        return WriteOp(apply=apply, job_id=job_id, status_changed=True, engine=engine)

    def _on_write_failed(self, job_ids: set[int]) -> None:
        for job_id in job_ids:
            runner = self.runners.get(job_id)
            if runner is not None and runner.stop_requested is None:
                runner.request_stop("pause", reasons.WRITE_FAILED, reasons.WRITE_FAILED_TEXT, engine=False)
            elif runner is None:
                self.writer.submit(self.pause_op(job_id, reasons.WRITE_FAILED, reasons.WRITE_FAILED_TEXT,
                                                 engine=False))

    # ---- 程序退出、开发模式重置 ----

    async def pause_all(self) -> int:
        """02 第 5.7 节第 1 步：排队和运行中的任务写为 paused（原因码 shutdown），返回暂停的任务数。"""

        async def apply(session: AsyncSession, _w: ResultWriter, op: WriteOp) -> int:
            ids = [
                int(i)
                for i in (
                    await session.execute(select(JobRow.id).where(JobRow.status.in_(("queued", "running"))))
                ).scalars()
            ]
            if ids:
                await session.execute(
                    update(JobRow)
                    .where(JobRow.id.in_(ids))
                    .values(status="paused", status_reason=reasons.SHUTDOWN_TEXT,
                            status_reason_code=reasons.SHUTDOWN, updated_at=now_iso())
                )
            return ids

        paused: list[int] = await self.writer.run(apply, job_event="none")
        for runner in list(self.runners.values()):
            runner.request_stop("pause", reasons.SHUTDOWN, reasons.SHUTDOWN_TEXT, write=False)
        for job_id in paused:   # 已提交，再发事件
            self.bus.job_changed(job_id, status_changed=True)
        self.update_running_count()
        return len(paused)

    async def _drain(self, timeout: float) -> None:
        """等执行器把进行中的条目做完，超时后取消剩余的（被打断的条目放回 pending）。"""
        tasks = [r.task for r in self.runners.values() if r.task is not None and not r.task.done()]
        if not tasks:
            return
        _done, pending = await asyncio.wait(tasks, timeout=timeout)
        if pending:
            for runner in list(self.runners.values()):
                runner.cancel_in_flight()
            _done, still = await asyncio.wait(pending, timeout=2.0)
            for task in still:
                task.cancel()
            if still:
                await asyncio.gather(*still, return_exceptions=True)

    async def shutdown(self) -> None:
        """02 第 5.7 节第 1–3 步，可以重复调用：暂停全部；最多等 3 秒让进行中的请求结束，之后取消剩余的；
        写入协程把队列全部提交。"""
        try:
            await self.pause_all()
        except Exception:  # noqa: BLE001 - 退出流程不能中断
            logger.exception("退出时暂停任务失败")
        await self._drain(SHUTDOWN_GRACE_SECONDS)
        await self.writer.flush()

    async def stop_all(self) -> None:
        """开发模式重置（04 第 3.1 节 /api/_dev/reset）：停止全部执行器，不改任务状态（随后会清空）。"""
        for runner in list(self.runners.values()):
            runner.request_stop("cancel")
        await self._drain(5.0)
        await self.writer.flush()
        self.runners.clear()
        self.update_running_count()
