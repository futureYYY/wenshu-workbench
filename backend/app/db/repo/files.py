"""files 表。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FileRow
from app.utils import now_iso


async def get(session: AsyncSession, file_id: int) -> FileRow | None:
    return await session.get(FileRow, file_id)


async def get_by_sha(session: AsyncSession, sha256: str) -> FileRow | None:
    return (await session.execute(select(FileRow).where(FileRow.sha256 == sha256))).scalar_one_or_none()


async def insert(session: AsyncSession, **fields: Any) -> FileRow:
    now = now_iso()
    row = FileRow(created_at=now, last_used_at=now, **fields)
    session.add(row)
    await session.flush()
    return row


async def touch(session: AsyncSession, file_id: int) -> None:
    await session.execute(update(FileRow).where(FileRow.id == file_id).values(last_used_at=now_iso()))


async def list_recent(session: AsyncSession, offset: int, limit: int) -> tuple[list[FileRow], int]:
    total = (await session.execute(select(func.count()).select_from(FileRow))).scalar_one()
    stmt = select(FileRow).order_by(FileRow.last_used_at.desc(), FileRow.id.desc()).offset(offset).limit(limit)
    return list((await session.execute(stmt)).scalars().all()), int(total)


async def delete_file(session: AsyncSession, file_id: int) -> None:
    await session.execute(delete(FileRow).where(FileRow.id == file_id))
