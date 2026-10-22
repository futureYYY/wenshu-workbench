"""jobs 表。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobItemRow, JobRow
from app.utils import now_iso

ACTIVE_STATUSES = ("queued", "running", "paused")


async def get(session: AsyncSession, job_id: int) -> JobRow | None:
    return await session.get(JobRow, job_id)


async def insert(session: AsyncSession, **fields: Any) -> JobRow:
    now = now_iso()
    row = JobRow(created_at=now, updated_at=now, **fields)
    session.add(row)
    await session.flush()
    return row


async def update_fields(session: AsyncSession, job_id: int, **fields: Any) -> None:
    fields["updated_at"] = now_iso()
    await session.execute(update(JobRow).where(JobRow.id == job_id).values(**fields))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_jobs(
    session: AsyncSession,
    *,
    statuses: list[str] | None,
    task_type: str | None,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[list[JobRow], int]:
    conditions = []
    if statuses:
        conditions.append(JobRow.status.in_(statuses))
    if task_type:
        conditions.append(JobRow.task_type == task_type)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        conditions.append(or_(JobRow.name.like(pattern, escape="\\"), JobRow.file_name.like(pattern, escape="\\")))
    total = (await session.execute(select(func.count()).select_from(JobRow).where(*conditions))).scalar_one()
    stmt = (
        select(JobRow)
        .where(*conditions)
        .order_by(JobRow.created_at.desc(), JobRow.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all()), int(total)


async def recount(session: AsyncSession, job_id: int) -> None:
    """03 第 7 节：按真实数据重算计数，防止漂移。"""
    await session.execute(
        text(
            "UPDATE jobs SET "
            "succeeded_count = (SELECT COUNT(*) FROM job_items WHERE job_id = :id AND status = 'succeeded'), "
            "failed_count = (SELECT COUNT(*) FROM job_items WHERE job_id = :id AND status = 'failed'), "
            "skipped_count = (SELECT COUNT(*) FROM job_items WHERE job_id = :id AND status = 'skipped') "
            "WHERE id = :id"
        ),
        {"id": job_id},
    )


async def reset_running_items(session: AsyncSession) -> None:
    await session.execute(update(JobItemRow).where(JobItemRow.status == "running").values(status="pending"))


async def add_delta(
    session: AsyncSession,
    job_id: int,
    *,
    succeeded: int = 0,
    failed: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    if not (succeeded or failed or prompt_tokens or completion_tokens):
        return
    await session.execute(
        update(JobRow)
        .where(JobRow.id == job_id)
        .values(
            succeeded_count=JobRow.succeeded_count + succeeded,
            failed_count=JobRow.failed_count + failed,
            prompt_tokens=JobRow.prompt_tokens + prompt_tokens,
            completion_tokens=JobRow.completion_tokens + completion_tokens,
            updated_at=now_iso(),
        )
    )


async def delete_job(session: AsyncSession, job_id: int) -> None:
    await session.execute(delete(JobRow).where(JobRow.id == job_id))


async def incremental_vacuum(session: AsyncSession) -> None:
    await session.execute(text("PRAGMA incremental_vacuum"))


async def active_count_for_file(session: AsyncSession, file_id: int) -> int:
    stmt = select(func.count()).select_from(JobRow).where(JobRow.file_id == file_id, JobRow.status.in_(ACTIVE_STATUSES))
    return int((await session.execute(stmt)).scalar_one())


async def has_pending_items(session: AsyncSession, job_id: int) -> bool:
    stmt = select(JobItemRow.id).where(JobItemRow.job_id == job_id, JobItemRow.status.in_(("pending", "running"))).limit(1)
    return (await session.execute(stmt)).first() is not None
