"""model_configs 表。"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobRow, ModelConfigRow
from app.utils import now_iso

ACTIVE_JOB_STATUSES = ("queued", "running", "paused")


async def get(session: AsyncSession, model_id: int) -> ModelConfigRow | None:
    return await session.get(ModelConfigRow, model_id)


async def get_by_name(session: AsyncSession, name: str) -> ModelConfigRow | None:
    return (await session.execute(select(ModelConfigRow).where(ModelConfigRow.name == name))).scalar_one_or_none()


async def get_demo(session: AsyncSession) -> ModelConfigRow | None:
    stmt = select(ModelConfigRow).where(ModelConfigRow.provider_kind == "demo").order_by(ModelConfigRow.id).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_all(session: AsyncSession) -> list[ModelConfigRow]:
    """真实模型按创建顺序在前，演示模型排在最后。"""
    demo_last = case((ModelConfigRow.provider_kind == "demo", 1), else_=0)
    stmt = select(ModelConfigRow).order_by(demo_last, ModelConfigRow.id)
    return list((await session.execute(stmt)).scalars().all())


async def insert(session: AsyncSession, **fields: Any) -> ModelConfigRow:
    now = now_iso()
    row = ModelConfigRow(created_at=now, updated_at=now, **fields)
    session.add(row)
    await session.flush()
    return row


async def update_fields(session: AsyncSession, row: ModelConfigRow, fields: dict[str, Any]) -> ModelConfigRow:
    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_at = now_iso()
    await session.flush()
    return row


async def delete_model(session: AsyncSession, model_id: int) -> None:
    await session.execute(delete(ModelConfigRow).where(ModelConfigRow.id == model_id))


async def active_job_counts(session: AsyncSession) -> dict[int, int]:
    stmt = (
        select(JobRow.model_id, func.count())
        .where(JobRow.model_id.is_not(None), JobRow.status.in_(ACTIVE_JOB_STATUSES))
        .group_by(JobRow.model_id)
    )
    return {int(mid): int(n) for mid, n in (await session.execute(stmt)).all()}


async def record_test(
    session: AsyncSession, model_id: int, *, ok: bool, latency_ms: int | None, message: str
) -> None:
    # 测试结果不算“修改配置”，不改 updated_at，避免模型客户端缓存被无谓重建
    await session.execute(
        update(ModelConfigRow)
        .where(ModelConfigRow.id == model_id)
        .values(last_test_at=now_iso(), last_test_ok=ok, last_test_latency_ms=latency_ms, last_test_message=message)
    )


async def update_avg_latency(session: AsyncSession, model_id: int, latencies: Sequence[int]) -> None:
    """05 第 6.4 节：每次成功的请求，新值 = 旧值 × 0.8 + 本次 × 0.2（旧值为空时直接取本次）。

    写入协程按批调用：一批里同一模型的多次耗时按先后依次代入，每步四舍五入取整，只读写一次数据库。"""
    if not latencies:
        return
    current = (
        await session.execute(select(ModelConfigRow.avg_latency_ms).where(ModelConfigRow.id == model_id))
    ).scalar_one_or_none()
    value: int | None = current
    for latency_ms in latencies:
        # 与 SQLite 的 ROUND 一致：半数远离零取整（耗时不为负）
        value = int(latency_ms) if value is None else int(math.floor(value * 0.8 + latency_ms * 0.2 + 0.5))
    await session.execute(update(ModelConfigRow).where(ModelConfigRow.id == model_id).values(avg_latency_ms=value))
