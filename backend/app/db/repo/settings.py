"""settings 表：每个 key 一行，value_json 存 JSON 值。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SettingRow
from app.utils import dumps, loads, now_iso


async def load_all(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(SettingRow))).scalars().all()
    return {row.key: loads(row.value_json) for row in rows}


async def get_value(session: AsyncSession, key: str, default: Any = None) -> Any:
    row = await session.get(SettingRow, key)
    return loads(row.value_json, default) if row else default


async def set_values(session: AsyncSession, values: dict[str, Any]) -> None:
    now = now_iso()
    for key, value in values.items():
        stmt = sqlite_insert(SettingRow).values(key=key, value_json=dumps(value), updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SettingRow.key],
            set_={"value_json": stmt.excluded.value_json, "updated_at": stmt.excluded.updated_at},
        )
        await session.execute(stmt)


async def insert_missing(session: AsyncSession, values: dict[str, Any]) -> list[str]:
    """只补齐缺失的 key，已有的不动。返回新插入的 key。"""
    existing = set((await session.execute(select(SettingRow.key))).scalars().all())
    now = now_iso()
    added: list[str] = []
    for key, value in values.items():
        if key in existing:
            continue
        session.add(SettingRow(key=key, value_json=dumps(value), updated_at=now))
        added.append(key)
    await session.flush()
    return added
