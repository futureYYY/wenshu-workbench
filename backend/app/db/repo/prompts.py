"""prompt_templates 与 prompt_versions 表。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobRow, PromptTemplateRow, PromptVersionRow
from app.utils import dumps, loads, now_iso


async def get(session: AsyncSession, prompt_id: int) -> PromptTemplateRow | None:
    return await session.get(PromptTemplateRow, prompt_id)


async def get_by_builtin_key(session: AsyncSession, key: str) -> PromptTemplateRow | None:
    stmt = select(PromptTemplateRow).where(PromptTemplateRow.builtin_key == key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_name(session: AsyncSession, task_type: str, name: str) -> PromptTemplateRow | None:
    stmt = select(PromptTemplateRow).where(PromptTemplateRow.task_type == task_type, PromptTemplateRow.name == name)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_templates(session: AsyncSession, task_type: str | None) -> list[PromptTemplateRow]:
    """内置在前，其余按修改时间倒序（“默认在最前”由服务层按设置再排一次）。"""
    builtin_first = case((PromptTemplateRow.is_builtin.is_(True), 0), else_=1)
    stmt = select(PromptTemplateRow)
    if task_type:
        stmt = stmt.where(PromptTemplateRow.task_type == task_type)
    stmt = stmt.order_by(PromptTemplateRow.task_type, builtin_first, PromptTemplateRow.updated_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def insert(session: AsyncSession, **fields: Any) -> PromptTemplateRow:
    now = now_iso()
    row = PromptTemplateRow(created_at=now, updated_at=now, **fields)
    session.add(row)
    await session.flush()
    return row


async def update_fields(session: AsyncSession, row: PromptTemplateRow, fields: dict[str, Any]) -> None:
    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_at = now_iso()
    await session.flush()


async def delete_template(session: AsyncSession, prompt_id: int) -> None:
    await session.execute(delete(PromptTemplateRow).where(PromptTemplateRow.id == prompt_id))


async def add_version(session: AsyncSession, prompt_id: int, version: int, snapshot: dict[str, Any], note: str) -> None:
    session.add(
        PromptVersionRow(
            prompt_id=prompt_id, version=version, snapshot_json=dumps(snapshot), note=note, created_at=now_iso()
        )
    )
    await session.flush()


async def list_versions(session: AsyncSession, prompt_id: int) -> list[PromptVersionRow]:
    stmt = (
        select(PromptVersionRow)
        .where(PromptVersionRow.prompt_id == prompt_id)
        .order_by(PromptVersionRow.version.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_version(session: AsyncSession, prompt_id: int, version: int) -> PromptVersionRow | None:
    stmt = select(PromptVersionRow).where(PromptVersionRow.prompt_id == prompt_id, PromptVersionRow.version == version)
    return (await session.execute(stmt)).scalar_one_or_none()


async def used_by_jobs(session: AsyncSession) -> dict[int, int]:
    stmt = select(JobRow.prompt_id, func.count()).where(JobRow.prompt_id.is_not(None)).group_by(JobRow.prompt_id)
    return {int(pid): int(n) for pid, n in (await session.execute(stmt)).all()}


def snapshot_of(row: PromptTemplateRow) -> dict[str, Any]:
    """03 第 4.3 节的快照结构。"""
    return {
        "id": row.id,
        "name": row.name,
        "version": row.version,
        "task_type": row.task_type,
        "system_prompt": row.system_prompt,
        "user_template": row.user_template,
        "chunk_template": row.chunk_template,
        "merge_template": row.merge_template,
        "output_mode": row.output_mode,
        "field_map": loads(row.field_map_json, {}),
        "temperature": row.temperature,
        "max_output_tokens": row.max_output_tokens,
    }
