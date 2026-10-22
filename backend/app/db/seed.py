"""启动时的初始化（03 第 8 节），每次启动都执行，幂等。

1. 两个内置模板（按 builtin_key），不存在则插入并写入版本 1；
2. 演示模型；
3. 补齐缺失的设置项（默认模型、默认提示词填实际 id）；
4. 默认自定义模型：导入本机配置或生成占位条目（使用者要求，见 services/model_service.py）；
5. 恢复异常中断的任务，并重算这些任务（以及所有未结束任务）的计数。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import Database
from app.db.models import JobRow
from app.db.repo import jobs as jobs_repo
from app.db.repo import prompts as prompts_repo
from app.db.repo import settings as settings_repo
from app.services import model_service
from app.services.crypto import Crypto
from app.services.defaults import BUILTIN_KEY_BY_TASK, BUILTIN_PROMPTS, DEFAULT_SETTINGS
from app.services.job_engine.reasons import SHUTDOWN, SHUTDOWN_TEXT
from app.utils import dumps, now_iso

logger = logging.getLogger(__name__)


async def ensure_builtin_prompts(db_session: AsyncSession) -> dict[str, int]:
    ids: dict[str, int] = {}
    for key, data in BUILTIN_PROMPTS.items():
        row = await prompts_repo.get_by_builtin_key(db_session, key)
        if row is None:
            name = data["name"]
            if await prompts_repo.get_by_name(db_session, data["task_type"], name):
                name = f"{name}（内置）"
            row = await prompts_repo.insert(
                db_session,
                task_type=data["task_type"],
                name=name,
                description=data["description"],
                system_prompt=data["system_prompt"],
                user_template=data["user_template"],
                chunk_template=data["chunk_template"],
                merge_template=data["merge_template"],
                output_mode=data["output_mode"],
                field_map_json=dumps(data["field_map"]),
                temperature=data["temperature"],
                max_output_tokens=data["max_output_tokens"],
                is_builtin=True,
                builtin_key=key,
                version=1,
            )
            await prompts_repo.add_version(db_session, row.id, 1, prompts_repo.snapshot_of(row), "内置默认")
            logger.info("已写入内置提示词“%s”", name)
        ids[data["task_type"]] = row.id
    return ids


async def run_seed(db: Database, crypto: Crypto, models_file: Path, *, fresh_db: bool) -> None:
    async with db.session() as session, session.begin():
        prompt_ids = await ensure_builtin_prompts(session)
        demo = await model_service.ensure_demo_model(session)

        defaults = dict(DEFAULT_SETTINGS)
        for task in ("classify", "summarize"):
            defaults[f"default_model_id.{task}"] = demo.id
            defaults[f"default_prompt_id.{task}"] = prompt_ids[task]
        await settings_repo.insert_missing(session, defaults)

        # 默认提示词指向的模板被删掉时，改回该类型的内置模板
        values = await settings_repo.load_all(session)
        repaired: dict[str, int] = {}
        for task, key in BUILTIN_KEY_BY_TASK.items():
            current = values.get(f"default_prompt_id.{task}")
            row = await prompts_repo.get(session, int(current)) if isinstance(current, int) else None
            if row is None or row.task_type != task:
                builtin = await prompts_repo.get_by_builtin_key(session, key)
                if builtin is not None:
                    repaired[f"default_prompt_id.{task}"] = builtin.id
        if repaired:
            await settings_repo.set_values(session, repaired)

        await model_service.prepare_custom_model(session, crypto, models_file, fresh_db)

    # 恢复异常中断的任务（单独一个事务）
    async with db.session() as session, session.begin():
        now = now_iso()
        recovered = list(
            (
                await session.execute(select(JobRow.id).where(JobRow.status.in_(("queued", "running"))))
            ).scalars()
        )
        if recovered:
            await session.execute(
                update(JobRow)
                .where(JobRow.id.in_(recovered))
                .values(status="paused", status_reason=SHUTDOWN_TEXT, status_reason_code=SHUTDOWN, updated_at=now)
            )
            logger.info("恢复了 %d 个异常中断的任务：%s", len(recovered), recovered)
        await jobs_repo.reset_running_items(session)
        unfinished = list(
            (
                await session.execute(select(JobRow.id).where(JobRow.status.not_in(("completed", "cancelled"))))
            ).scalars()
        )
        for job_id in unfinished:
            await jobs_repo.recount(session, job_id)


def clean_exports(exports_dir: Path, max_age_seconds: int = 24 * 3600) -> int:
    """启动时清理 24 小时前的导出文件（03 第 10 节）。"""
    removed = 0
    if not exports_dir.is_dir():
        return 0
    cutoff = time.time() - max_age_seconds
    for path in exports_dir.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            logger.debug("清理导出文件失败：%s", path, exc_info=True)
    return removed
