"""任务与条目的查询、组装和修改（04 第 8 节；03 第 7 节派生值）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import conflict, not_found
from app.context import AppContext
from app.db.models import JobItemRow, JobRow, ModelConfigRow
from app.db.repo import items as items_repo
from app.db.repo import jobs as jobs_repo
from app.db.repo import models as models_repo
from app.schemas.common import ChatMessage, KeyPoint, Usage
from app.schemas.jobs import (
    AttemptLogEntry,
    CategoryList,
    CategoryStat,
    Compression,
    ItemDetail,
    ItemPage,
    ItemPatch,
    ItemSummary,
    Job,
    JobColumn,
    JobLive,
    JobPage,
    JobPatch,
    JobProgress,
    JobSource,
    JobSummary,
    Track,
)
from app.services import review, segmenter
from app.services.job_engine.manager import JobManager
from app.services.job_engine.writer import ResultWriter, WriteOp
from app.services.prompt_render import (
    ContextTooSmall,
    MissingTemplate,
    PromptSpec,
    RowContext,
    assemble,
    budget_factor,
    chunk_messages,
    effective_max_output,
    plan_classify,
    plan_summarize,
    summarize_main_stage,
)
from app.utils import loads

VALID_JOB_STATUSES = ("queued", "running", "paused", "completed", "cancelled")
VALID_ITEM_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")
_MISSING = object()


def split_csv(value: str | None, allowed: tuple[str, ...]) -> list[str]:
    if not value:
        return []
    return [v for v in (p.strip() for p in value.split(",")) if v in allowed]


# ---- 任务 ----


def _snapshot_name(row: JobRow, field: str) -> str:
    data = loads(getattr(row, field), {}) or {}
    return str(data.get("name") or "")


def progress_of(row: JobRow, manager: JobManager) -> JobProgress:
    """03 第 7 节：pending = total − succeeded − failed − skipped − running；百分比、速度、预计剩余秒数。"""
    running, rate = manager.runtime(row.id)
    total = int(row.total_items)
    done = int(row.succeeded_count) + int(row.failed_count) + int(row.skipped_count)
    pending = max(0, total - done - running)
    percent = round(done / total * 100, 1) if total else 0.0
    if row.status != "running":
        rate = None
    eta = round((pending + running) / rate * 60) if rate else None
    return JobProgress(
        total=total,
        pending=pending,
        running=running,
        succeeded=int(row.succeeded_count),
        failed=int(row.failed_count),
        skipped=int(row.skipped_count),
        percent=percent,
        rate_per_min=rate,
        eta_seconds=eta,
    )


def _summary_fields(row: JobRow, manager: JobManager) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "task_type": row.task_type,
        "status": row.status,
        "status_reason": row.status_reason or "",
        "status_reason_code": row.status_reason_code,
        "file_name": row.file_name,
        "model_name": _snapshot_name(row, "model_snapshot_json"),
        "prompt_name": _snapshot_name(row, "prompt_snapshot_json"),
        "prompt_version": int(row.prompt_version),
        "concurrency": int(row.concurrency),
        "progress": progress_of(row, manager),
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "updated_at": row.updated_at,
    }


def summary_of(row: JobRow, manager: JobManager) -> JobSummary:
    return JobSummary(**_summary_fields(row, manager))


def aliases_of(row: JobRow) -> dict[str, str]:
    return {str(k): str(v) for k, v in (loads(row.category_aliases_json, {}) or {}).items()}


async def categories_of(session: AsyncSession, row: JobRow) -> list[CategoryStat]:
    colors = {str(k): int(v) for k, v in (loads(row.category_colors_json, {}) or {}).items()}
    counts = await items_repo.category_counts(session, row.id, aliases_of(row))
    succeeded = max(1, int(row.succeeded_count))
    stats = [
        CategoryStat(
            label=label,
            count=count,
            percent=round(count / succeeded * 100, 1),
            color_index=colors.get(label, -1),
        )
        for label, count in counts
    ]
    stats.sort(key=lambda s: (-s.count, s.color_index if s.color_index >= 0 else 99, s.label))
    return stats


async def live_fields(session: AsyncSession, row: JobRow, manager: JobManager) -> dict[str, Any]:
    fields = _summary_fields(row, manager)
    fields["usage"] = Usage(prompt_tokens=int(row.prompt_tokens), completion_tokens=int(row.completion_tokens))
    fields["categories"] = await categories_of(session, row) if row.task_type == "classify" else None
    if row.task_type == "summarize":
        input_chars, output_chars = await items_repo.compression_totals(session, row.id)
        ratio = round(input_chars / output_chars, 1) if output_chars else None
        fields["compression"] = Compression(input_chars=input_chars, output_chars=output_chars, ratio=ratio)
    else:
        fields["compression"] = None
    return fields


async def live_of(session: AsyncSession, row: JobRow, manager: JobManager) -> JobLive:
    return JobLive(**await live_fields(session, row, manager))


def source_of(row: JobRow) -> JobSource:
    data = loads(row.source_json, {}) or {}
    columns = [
        JobColumn(key=str(c.get("key")), title=str(c.get("title")), letter=c.get("letter"), index=int(c.get("index", i)))
        for i, c in enumerate(data.get("columns") or [])
    ]
    return JobSource(
        sheet=data.get("sheet"),
        header_row=int(data.get("header_row") or 0),
        text_columns=[str(c) for c in data.get("text_columns") or []],
        join_mode="plain" if data.get("join_mode") == "plain" else "labeled",
        start_row=data.get("start_row"),
        limit=data.get("limit"),
        split_mode="line",
        columns=columns,
    )


async def job_of(session: AsyncSession, row: JobRow, manager: JobManager) -> Job:
    fields = await live_fields(session, row, manager)
    return Job(
        **fields,
        file_id=row.file_id,
        source=source_of(row),
        prompt_id=row.prompt_id,
        prompt_snapshot=loads(row.prompt_snapshot_json, {}) or {},
        model_id=row.model_id,
        model_snapshot=loads(row.model_snapshot_json, {}) or {},
        max_retries=int(row.max_retries),
        dedupe=bool(row.dedupe),
        label_options=review.label_options(row),
    )


async def require_job(session: AsyncSession, job_id: int) -> JobRow:
    row = await jobs_repo.get(session, job_id)
    if row is None:
        raise not_found("任务不存在")
    return row


async def get_job(ctx: AppContext, job_id: int) -> Job:
    async with ctx.db.session() as session:
        return await job_of(session, await require_job(session, job_id), ctx.manager)


async def get_summary(ctx: AppContext, job_id: int) -> JobSummary | None:
    async with ctx.db.session() as session:
        row = await jobs_repo.get(session, job_id)
        return summary_of(row, ctx.manager) if row is not None else None


async def get_live(ctx: AppContext, job_id: int) -> JobLive | None:
    async with ctx.db.session() as session:
        row = await jobs_repo.get(session, job_id)
        return await live_of(session, row, ctx.manager) if row is not None else None


async def list_jobs(
    ctx: AppContext, *, status: str | None, task_type: str | None, q: str | None, offset: int, limit: int
) -> JobPage:
    async with ctx.db.session() as session:
        rows, total = await jobs_repo.list_jobs(
            session,
            statuses=split_csv(status, VALID_JOB_STATUSES) or None,
            task_type=task_type,
            q=q,
            offset=offset,
            limit=limit,
        )
    return JobPage(items=[summary_of(r, ctx.manager) for r in rows], total=total)


async def patch_job(ctx: AppContext, job_id: int, body: JobPatch) -> Job:
    provided = body.model_fields_set

    async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> None:
        row = await require_job(session, job_id)
        fields: dict[str, Any] = {}
        if "name" in provided and body.name is not None:
            fields["name"] = body.name
        if "concurrency" in provided and body.concurrency is not None and body.concurrency != row.concurrency:
            if row.status in ("queued", "running"):
                raise conflict("JOB_STATE_CONFLICT", "运行中不能修改并发，请先暂停（运行中调整并发在第二期支持）")
            fields["concurrency"] = body.concurrency
        if fields:
            await jobs_repo.update_fields(session, job_id, **fields)

    await ctx.writer.run(apply, job_id=job_id)
    return await get_job(ctx, job_id)


# ---- 条目 ----


def item_summary(row: Any, aliases: dict[str, str]) -> ItemSummary:
    """row 可以是摘要查询的行（含 input_head、summary_head、summary_edited、effective_output_chars），
    也可以是完整的 JobItemRow。摘要、字数和压缩比都按有效摘要（人工修改过的取修改后的，03 第 7 节）给出。"""
    head = getattr(row, "input_head", None)
    if head is None:
        head = (row.input_text or "")[:200]
    edited = getattr(row, "summary_edited", _MISSING)
    if edited is _MISSING:      # 完整的 JobItemRow
        edited = row.manual_summary is not None
        text = review.effective_summary(row.summary, row.manual_summary)
        summary_head = text[:200] if text else None
        output_chars = review.effective_output_chars(row.output_chars, row.summary, row.manual_summary)
    else:
        edited = bool(edited)
        summary_head = row.summary_head
        output_chars = row.effective_output_chars
    label = row.label
    effective = row.manual_label or (aliases.get(label, label) if label else None)
    ratio = round(row.input_chars / output_chars, 1) if output_chars else None
    return ItemSummary(
        id=row.id,
        seq=row.seq,
        row_number=row.row_number,
        status=row.status,
        input_preview=head.replace("\r", " ").replace("\n", " "),
        input_chars=int(row.input_chars),
        label=label,
        effective_label=effective,
        manual_label=row.manual_label,
        corrected=row.manual_label is not None or edited,
        confidence=row.confidence,
        reason=row.reason,
        summary_preview=summary_head.replace("\r", " ").replace("\n", " ") if summary_head else None,
        output_chars=output_chars,
        compression_ratio=ratio,
        truncated=bool(row.truncated),
        chunk_count=int(row.chunk_count or 1),
        attempts=int(row.attempts or 0),
        latency_ms=row.latency_ms,
        error_code=row.error_code,
        error_message=row.error_message,
        reviewed=bool(row.reviewed),
        dedup_of=row.dedup_of,
        finished_at=row.finished_at,
    )


def build_filters(
    status: str | None,
    labels: list[str] | None,
    q: str | None,
    reviewed: bool | None,
    corrected: bool | None = None,
) -> items_repo.ItemFilters:
    return items_repo.ItemFilters(
        statuses=split_csv(status, VALID_ITEM_STATUSES),
        labels=[label for label in (labels or []) if label],
        q=q,
        reviewed=reviewed,
        corrected=corrected,
    )


async def list_items(
    ctx: AppContext,
    job_id: int,
    filters: items_repo.ItemFilters,
    *,
    order: str,
    offset: int,
    limit: int,
) -> ItemPage:
    async with ctx.db.session() as session:
        job = await require_job(session, job_id)
        aliases = aliases_of(job)
        rows, total = await items_repo.list_summaries(
            session, job_id, filters, aliases, order=order, offset=offset, limit=limit
        )
    return ItemPage(items=[item_summary(r, aliases) for r in rows], total=total)


async def summaries_by_ids(ctx: AppContext, job_id: int, ids: list[int]) -> list[ItemSummary]:
    async with ctx.db.session() as session:
        job = await jobs_repo.get(session, job_id)
        if job is None:
            return []
        rows = await items_repo.summaries_by_ids(session, ids)
    aliases = aliases_of(job)
    return [item_summary(r, aliases) for r in rows if r.job_id == job_id]


def _row_context(job: JobRow, item: JobItemRow, today: str | None = None) -> RowContext:
    source = loads(job.source_json, {}) or {}
    return RowContext(
        text=item.input_text,
        row_number=item.row_number,
        file_name=job.file_name,
        row_values={str(k): str(v) for k, v in (loads(item.row_values_json, {}) or {}).items()},
        columns=[(str(c.get("key")), str(c.get("title"))) for c in source.get("columns") or []],
        today=today,
    )


def rerender_messages(job: JobRow, item: JobItemRow, current_model: ModelConfigRow | None) -> list[dict[str, str]]:
    """按任务快照和该条目的 render_meta（03 第 4.7 节）重新渲染，与当时实际发送的一致；分段时为第一段的消息。
    还没处理过的条目（没有 render_meta）按当前模型配置渲染；模型已被删除时用任务快照里的配置。"""
    spec = PromptSpec.from_mapping(loads(job.prompt_snapshot_json, {}) or {})
    meta = loads(item.render_meta_json, None)
    if isinstance(meta, dict) and meta.get("context_window") and meta.get("max_output_tokens"):
        context_window = int(meta["context_window"])
        max_output = int(meta["max_output_tokens"])
        today = str(meta["today"]) if meta.get("today") else None
        input_budget = meta.get("input_budget")
    else:
        if current_model is not None:
            window, model_max = current_model.context_window, current_model.max_output_tokens
        else:
            snapshot = loads(job.model_snapshot_json, {}) or {}
            window, model_max = snapshot.get("context_window"), snapshot.get("max_output_tokens")
        context_window = int(window or 32768)
        max_output = effective_max_output(spec, int(model_max or 1024))
        today = None
        input_budget = None
    row = _row_context(job, item, today)
    try:
        factor = budget_factor(spec, row, context_window, max_output,
                               int(input_budget) if isinstance(input_budget, int) else None)
        if spec.task_type == "classify":
            return plan_classify(spec, row, context_window, max_output, factor).messages.messages
        plan = plan_summarize(spec, row, context_window, max_output, factor)
        if plan.single is not None:
            return plan.single.messages
        return chunk_messages(spec, row, plan.chunks[0], 1, len(plan.chunks)).messages
    except (ContextTooSmall, MissingTemplate):
        stage = summarize_main_stage(row, segmenter.split_segments(row.text))
        return assemble(spec, spec.user_template, row, stage, "user").messages


def _key_points(value: str | None) -> list[KeyPoint] | None:
    data = loads(value, None)
    if not isinstance(data, list):
        return None
    points: list[KeyPoint] = []
    for element in data:
        if isinstance(element, dict) and element.get("text"):
            points.append(
                KeyPoint(text=str(element["text"]), sources=[int(s) for s in element.get("sources") or [] if isinstance(s, int)])
            )
    return points


def _attempt_log(value: str | None) -> list[AttemptLogEntry]:
    entries: list[AttemptLogEntry] = []
    for raw in loads(value, []) or []:
        if not isinstance(raw, dict):
            continue
        entries.append(
            AttemptLogEntry(
                at=str(raw.get("at") or ""),
                attempt=int(raw.get("attempt") or 0),
                phase=str(raw.get("phase") or "request"),
                status_code=raw.get("status_code"),
                error_code=raw.get("error_code"),
                message=str(raw.get("message") or ""),
                latency_ms=raw.get("latency_ms"),
            )
        )
    return entries


async def get_item(ctx: AppContext, job_id: int, item_id: int) -> ItemDetail:
    async with ctx.db.session() as session:
        job = await require_job(session, job_id)
        item = await items_repo.get_in_job(session, job_id, item_id)
        if item is None:
            raise not_found("条目不存在")
        current_model = await models_repo.get(session, job.model_id) if job.model_id is not None else None
    summary = item_summary(item, aliases_of(job))
    result = loads(item.result_json, None)
    return ItemDetail(
        **summary.model_dump(),
        input_text=item.input_text,
        row_values={str(k): str(v) for k, v in (loads(item.row_values_json, {}) or {}).items()},
        segments=segmenter.split_segments(item.input_text) if job.task_type == "summarize" else None,
        summary=item.summary,
        manual_summary=item.manual_summary,
        key_points=_key_points(item.key_points_json),
        result=result if isinstance(result, dict) else None,
        raw_output=item.raw_output,
        reasoning=item.reasoning,
        messages=[
            ChatMessage(role=m["role"], content=m["content"])  # type: ignore[arg-type]
            for m in rerender_messages(job, item, current_model)
        ],
        omitted_chars=item.omitted_chars,
        attempt_log=_attempt_log(item.attempt_log_json),
        model_used=item.model_used,
        prompt_tokens=item.prompt_tokens,
        completion_tokens=item.completion_tokens,
        note=item.note,
        manual_at=item.manual_at,
        started_at=item.started_at,
    )


async def item_summary_by_id(ctx: AppContext, job_id: int, item_id: int) -> ItemSummary:
    async with ctx.db.session() as session:
        job = await require_job(session, job_id)
        row = await items_repo.summary_by_id(session, item_id)
        if row is None or row.job_id != job_id:
            raise not_found("条目不存在")
        return item_summary(row, aliases_of(job))


async def patch_item(ctx: AppContext, job_id: int, item_id: int, body: ItemPatch) -> ItemSummary:
    """人工复核（04 第 8.2 节）：校验规则见 review.patch_values。"""

    async def apply(session: AsyncSession, writer: ResultWriter, _op: WriteOp) -> None:
        job = await require_job(session, job_id)
        item = await items_repo.get_in_job(session, job_id, item_id)
        if item is None:
            raise not_found("条目不存在")
        values = review.patch_values(job, item, body)
        await items_repo.patch_item(session, item_id, values)
        if values.get("manual_label"):
            # 修正成模型没给过的类别时也分配线路色（03 第 4.6 节），线网图里它和其他类别一样有颜色
            await writer.ensure_color(session, job_id, values["manual_label"])

    await ctx.writer.run(apply, job_id=job_id, item_ids=[item_id])
    return await item_summary_by_id(ctx, job_id, item_id)


async def get_categories(ctx: AppContext, job_id: int) -> CategoryList:
    async with ctx.db.session() as session:
        job = await require_job(session, job_id)
        items = await categories_of(session, job) if job.task_type == "classify" else []
        return CategoryList(items=items, failed=int(job.failed_count))


async def get_tracks(ctx: AppContext, job_id: int) -> list[Track]:
    async with ctx.db.session() as session:
        await require_job(session, job_id)
    return [Track(**t) for t in ctx.manager.tracks(job_id)]
