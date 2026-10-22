"""job_items 表。列表查询只取摘要需要的列（原文只取前 200 字），避免一次读入大段文本。"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ColumnElement, bindparam, case, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobItemRow

# 跟随条目同步时从主条目复制的字段（03 第 6.2 节，另加 truncated、chunk_count、model_used 便于显示一致）
FOLLOWER_FIELDS = (
    "status",
    "label",
    "confidence",
    "reason",
    "summary",
    "key_points_json",
    "output_chars",
    "result_json",
    "raw_output",
    "error_code",
    "error_message",
    "truncated",
    "omitted_chars",
    "chunk_count",
    "model_used",
    "finished_at",
)

# 重新处理时清空的结果字段
RESULT_RESET: dict[str, Any] = {
    "label": None,
    "confidence": None,
    "reason": None,
    "summary": None,
    "key_points_json": None,
    "output_chars": None,
    "result_json": None,
    "raw_output": None,
    "reasoning": None,
    "truncated": False,
    "omitted_chars": None,
    "render_meta_json": None,
    "chunk_count": 1,
    "error_code": None,
    "error_message": None,
    "prompt_tokens": None,
    "completion_tokens": None,
    "latency_ms": None,
    "started_at": None,
    "finished_at": None,
}

ORDER_COLUMNS = {
    "seq": JobItemRow.seq,
    "confidence": JobItemRow.confidence,
    "latency_ms": JobItemRow.latency_ms,
    "input_chars": JobItemRow.input_chars,
}


@dataclass
class ItemFilters:
    statuses: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    q: str | None = None
    reviewed: bool | None = None
    corrected: bool | None = None     # 意图或摘要有人工修正


def effective_label_expr(aliases: dict[str, str]) -> ColumnElement[Any]:
    """有效类别：manual_label 非空取它；否则若 label 在别名表里取别名；否则取 label。"""
    if aliases:
        aliased = case(*((JobItemRow.label == k, v) for k, v in aliases.items()), else_=JobItemRow.label)
        return func.coalesce(JobItemRow.manual_label, aliased)
    return func.coalesce(JobItemRow.manual_label, JobItemRow.label)


def corrected_expr() -> ColumnElement[bool]:
    return or_(JobItemRow.manual_label.is_not(None), JobItemRow.manual_summary.is_not(None))


def effective_output_chars_expr() -> ColumnElement[Any]:
    """有效摘要加要点的字数（03 第 7 节）：摘要修改过时把模型摘要的字数换成修改后的。"""
    return case(
        (
            JobItemRow.manual_summary.is_not(None),
            JobItemRow.output_chars - func.length(func.coalesce(JobItemRow.summary, "")) + func.length(JobItemRow.manual_summary),
        ),
        else_=JobItemRow.output_chars,
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filter_conditions(job_id: int, filters: ItemFilters, aliases: dict[str, str]) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [JobItemRow.job_id == job_id]
    if filters.statuses:
        conditions.append(JobItemRow.status.in_(filters.statuses))
    if filters.labels:
        conditions.append(effective_label_expr(aliases).in_(filters.labels))
    if filters.q and filters.q.strip():
        pattern = f"%{_escape_like(filters.q.strip())}%"
        conditions.append(
            or_(
                JobItemRow.input_text.like(pattern, escape="\\"),
                JobItemRow.label.like(pattern, escape="\\"),
                JobItemRow.manual_label.like(pattern, escape="\\"),
                JobItemRow.reason.like(pattern, escape="\\"),
                JobItemRow.summary.like(pattern, escape="\\"),
                JobItemRow.manual_summary.like(pattern, escape="\\"),
            )
        )
    if filters.reviewed is not None:
        conditions.append(JobItemRow.reviewed.is_(filters.reviewed))
    if filters.corrected is not None:
        conditions.append(corrected_expr() if filters.corrected else ~corrected_expr())
    return conditions


SUMMARY_COLUMNS = (
    JobItemRow.id,
    JobItemRow.job_id,
    JobItemRow.seq,
    JobItemRow.row_number,
    JobItemRow.status,
    func.substr(JobItemRow.input_text, 1, 200).label("input_head"),
    JobItemRow.input_chars,
    JobItemRow.label,
    JobItemRow.manual_label,
    JobItemRow.confidence,
    JobItemRow.reason,
    # 有效摘要（人工修改过的取修改后的）
    func.substr(func.coalesce(JobItemRow.manual_summary, JobItemRow.summary), 1, 200).label("summary_head"),
    JobItemRow.manual_summary.is_not(None).label("summary_edited"),
    effective_output_chars_expr().label("effective_output_chars"),
    JobItemRow.truncated,
    JobItemRow.chunk_count,
    JobItemRow.attempts,
    JobItemRow.latency_ms,
    JobItemRow.error_code,
    JobItemRow.error_message,
    JobItemRow.reviewed,
    JobItemRow.dedup_of,
    JobItemRow.finished_at,
)


async def list_summaries(
    session: AsyncSession,
    job_id: int,
    filters: ItemFilters,
    aliases: dict[str, str],
    *,
    order: str,
    offset: int,
    limit: int,
) -> tuple[list[Any], int]:
    conditions = filter_conditions(job_id, filters, aliases)
    total = (await session.execute(select(func.count()).select_from(JobItemRow).where(*conditions))).scalar_one()
    descending = order.startswith("-")
    column = ORDER_COLUMNS.get(order.lstrip("-"), JobItemRow.seq)
    primary = column.desc() if descending else column.asc()
    tiebreak = JobItemRow.seq.desc() if descending and column is JobItemRow.seq else JobItemRow.seq.asc()
    stmt = select(*SUMMARY_COLUMNS).where(*conditions).order_by(primary, tiebreak).offset(offset).limit(limit)
    rows = list((await session.execute(stmt)).all())
    return rows, int(total)


async def summaries_by_ids(session: AsyncSession, ids: Sequence[int]) -> list[Any]:
    if not ids:
        return []
    stmt = select(*SUMMARY_COLUMNS).where(JobItemRow.id.in_(list(ids))).order_by(JobItemRow.seq)
    return list((await session.execute(stmt)).all())


async def summary_by_id(session: AsyncSession, item_id: int) -> Any | None:
    stmt = select(*SUMMARY_COLUMNS).where(JobItemRow.id == item_id)
    return (await session.execute(stmt)).first()


async def get(session: AsyncSession, item_id: int) -> JobItemRow | None:
    return await session.get(JobItemRow, item_id)


async def get_in_job(session: AsyncSession, job_id: int, item_id: int) -> JobItemRow | None:
    row = await session.get(JobItemRow, item_id)
    return row if row is not None and row.job_id == job_id else None


async def insert_batch(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    """批量插入（executemany）。"""
    if rows:
        await session.execute(insert(JobItemRow), rows)


async def ids_for_seqs(session: AsyncSession, job_id: int, low: int, high: int) -> dict[int, int]:
    """seq → id。写入由写入协程串行执行，插入后立刻按 seq 查回 id 是确定的。"""
    stmt = select(JobItemRow.seq, JobItemRow.id).where(JobItemRow.job_id == job_id, JobItemRow.seq.between(low, high))
    return {int(seq): int(item_id) for seq, item_id in (await session.execute(stmt)).all()}


async def pending_leaders(
    session: AsyncSession, job_id: int, *, after_seq: int, exclude_ids: Collection[int], limit: int
) -> list[JobItemRow]:
    """02 第 5.2 节：键集分页取待处理的主条目（seq > after_seq，按 seq 升序），排除已派发、结果还没落库的。"""
    conditions: list[ColumnElement[bool]] = [
        JobItemRow.job_id == job_id,
        JobItemRow.status == "pending",
        JobItemRow.dedup_of.is_(None),
        JobItemRow.seq > after_seq,
    ]
    if exclude_ids:
        conditions.append(JobItemRow.id.not_in(list(exclude_ids)))
    stmt = select(JobItemRow).where(*conditions).order_by(JobItemRow.seq).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def reset_running(session: AsyncSession, job_id: int) -> int:
    """没有执行器时仍标着 running 的条目（例如结果写入失败）放回 pending。"""
    result = await session.execute(
        update(JobItemRow).where(JobItemRow.job_id == job_id, JobItemRow.status == "running").values(status="pending")
    )
    return int(result.rowcount or 0)


async def update_item(session: AsyncSession, item_id: int, values: dict[str, Any]) -> None:
    await session.execute(update(JobItemRow).where(JobItemRow.id == item_id).values(**values))


async def update_items(session: AsyncSession, updates: Mapping[int, Mapping[str, Any]]) -> None:
    """多条条目各自的字段更新（写入协程按批调用）：按字段组合分组，每组一条 executemany。

    异步驱动下每条 SQL 都要在线程和事件循环之间往返，一批 100 个写入逐条执行要几百次往返，
    引擎很快时（例如演示模型的 fast）写入会越积越多；合并后一批只需要几次往返。"""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for item_id, values in updates.items():
        if not values:
            continue
        keys = tuple(sorted(values))
        # 参数名加前缀：SQLAlchemy 不允许 bindparam 与 UPDATE 的列同名
        groups.setdefault(keys, []).append({"b_id": item_id, **{f"v_{k}": values[k] for k in keys}})
    if not groups:
        return
    table = JobItemRow.__table__
    connection = await session.connection()
    for keys, params in groups.items():
        stmt = update(table).where(table.c.id == bindparam("b_id")).values({k: bindparam(f"v_{k}") for k in keys})
        await connection.execute(stmt, params)


async def leaders_with_followers(session: AsyncSession, leader_ids: Collection[int]) -> set[int]:
    """这些主条目里哪些有跟随条目（一次查询；没有跟随条目的主条目不用同步）。"""
    if not leader_ids:
        return set()
    stmt = select(JobItemRow.dedup_of).where(JobItemRow.dedup_of.in_(list(leader_ids))).distinct()
    return {int(i) for i in (await session.execute(stmt)).scalars().all() if i is not None}


async def follower_status_counts(session: AsyncSession, leader_id: int) -> dict[str, int]:
    stmt = (
        select(JobItemRow.status, func.count())
        .where(JobItemRow.dedup_of == leader_id)
        .group_by(JobItemRow.status)
    )
    return {str(status): int(n) for status, n in (await session.execute(stmt)).all()}


async def follower_ids(session: AsyncSession, leader_id: int) -> list[int]:
    stmt = select(JobItemRow.id).where(JobItemRow.dedup_of == leader_id)
    return [int(i) for i in (await session.execute(stmt)).scalars().all()]


async def sync_followers(session: AsyncSession, leader_id: int, values: dict[str, Any]) -> dict[str, int]:
    """把主条目的状态和结果复制到全部跟随条目，attempts 记为 0。返回同步前各状态的条数。"""
    before = await follower_status_counts(session, leader_id)
    if before:
        copy = {k: values[k] for k in FOLLOWER_FIELDS if k in values}
        copy["attempts"] = 0
        await session.execute(update(JobItemRow).where(JobItemRow.dedup_of == leader_id).values(**copy))
    return before


async def orphan_follower_leaders(session: AsyncSession, job_id: int) -> list[JobItemRow]:
    """主条目已结束、但跟随条目仍是 pending 的主条目（崩溃等极端情况下的兜底）。"""
    leader = JobItemRow.__table__.alias("leader")
    stmt = (
        select(JobItemRow.dedup_of)
        .join(leader, leader.c.id == JobItemRow.dedup_of)
        .where(
            JobItemRow.job_id == job_id,
            JobItemRow.status == "pending",
            JobItemRow.dedup_of.is_not(None),
            leader.c.status.in_(("succeeded", "failed")),
        )
        .distinct()
    )
    ids = [int(i) for i in (await session.execute(stmt)).scalars().all()]
    if not ids:
        return []
    return list((await session.execute(select(JobItemRow).where(JobItemRow.id.in_(ids)))).scalars().all())


async def requeue_failed(session: AsyncSession, job_id: int) -> list[int]:
    ids = [
        int(i)
        for i in (
            await session.execute(
                select(JobItemRow.id).where(JobItemRow.job_id == job_id, JobItemRow.status == "failed")
            )
        ).scalars()
    ]
    if ids:
        await session.execute(
            update(JobItemRow)
            .where(JobItemRow.job_id == job_id, JobItemRow.status == "failed")
            .values(status="pending", error_code=None, error_message=None, finished_at=None)
        )
    return ids


async def requeue_item(session: AsyncSession, item_id: int, *, detach: bool) -> None:
    values: dict[str, Any] = {"status": "pending", **RESULT_RESET}
    if detach:
        values["dedup_of"] = None
    await session.execute(update(JobItemRow).where(JobItemRow.id == item_id).values(**values))


async def patch_item(session: AsyncSession, item_id: int, values: dict[str, Any]) -> None:
    if values:
        await session.execute(update(JobItemRow).where(JobItemRow.id == item_id).values(**values))


async def category_counts(session: AsyncSession, job_id: int, aliases: dict[str, str]) -> list[tuple[str, int]]:
    effective = effective_label_expr(aliases).label("effective")
    stmt = (
        select(effective, func.count())
        .where(JobItemRow.job_id == job_id, JobItemRow.status == "succeeded", effective_label_expr(aliases).is_not(None))
        .group_by(effective)
    )
    return [(str(label), int(n)) for label, n in (await session.execute(stmt)).all()]


async def status_counts(session: AsyncSession, job_id: int) -> dict[str, int]:
    stmt = select(JobItemRow.status, func.count()).where(JobItemRow.job_id == job_id).group_by(JobItemRow.status)
    return {str(s): int(n) for s, n in (await session.execute(stmt)).all()}


async def compression_totals(session: AsyncSession, job_id: int) -> tuple[int, int]:
    """已成功条目的原文、有效摘要字数合计（人工修改过的摘要按修改后的计）。"""
    stmt = select(func.coalesce(func.sum(JobItemRow.input_chars), 0), func.coalesce(func.sum(effective_output_chars_expr()), 0)).where(
        JobItemRow.job_id == job_id, JobItemRow.status == "succeeded", JobItemRow.output_chars.is_not(None)
    )
    row = (await session.execute(stmt)).one()
    return int(row[0] or 0), int(row[1] or 0)


async def export_page(
    session: AsyncSession, job_id: int, filters: ItemFilters, aliases: dict[str, str], after_seq: int, limit: int
) -> list[JobItemRow]:
    conditions = filter_conditions(job_id, filters, aliases)
    stmt = select(JobItemRow).where(*conditions, JobItemRow.seq > after_seq).order_by(JobItemRow.seq).limit(limit)
    return list((await session.execute(stmt)).scalars().all())
