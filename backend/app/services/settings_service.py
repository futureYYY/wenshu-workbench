"""设置的读取与部分更新（04 第 3.2 节、03 第 5 节）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import field_error
from app.config import MAX_CONCURRENCY, MAX_ROWS_PER_SOURCE, MAX_UPLOAD_BYTES
from app.db.engine import Database
from app.db.repo import models as models_repo
from app.db.repo import prompts as prompts_repo
from app.db.repo import settings as settings_repo
from app.schemas.system import (
    Settings,
    SettingsLimits,
    SettingsPatch,
    TaskConcurrency,
    TaskModelIds,
    TaskPromptIds,
)
from app.services.defaults import DEFAULT_SETTINGS

TASK_TYPES = ("classify", "summarize")


def _int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, number))


def _opt_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def build_settings(values: dict[str, Any]) -> Settings:
    """把 settings 表的键值组装成 Settings；库里的值不合法时退回默认值。"""

    def get(key: str) -> Any:
        return values.get(key, DEFAULT_SETTINGS.get(key))

    limit = get("default_limit")
    theme = get("theme")
    open_mode = get("open_mode")
    return Settings(
        default_concurrency=TaskConcurrency(
            classify=_int(get("default_concurrency.classify"), 5, 1, MAX_CONCURRENCY),
            summarize=_int(get("default_concurrency.summarize"), 5, 1, MAX_CONCURRENCY),
        ),
        default_limit=None if limit is None else _int(limit, 100, 1, MAX_ROWS_PER_SOURCE),
        default_max_retries=_int(get("default_max_retries"), 2, 0, 5),
        default_dedupe=bool(get("default_dedupe")),
        default_model_id=TaskModelIds(
            classify=_opt_int(get("default_model_id.classify")),
            summarize=_opt_int(get("default_model_id.summarize")),
        ),
        default_prompt_id=TaskPromptIds(
            classify=_int(get("default_prompt_id.classify"), 0, 0, 2**62),
            summarize=_int(get("default_prompt_id.summarize"), 0, 0, 2**62),
        ),
        theme=theme if theme in ("system", "light", "dark") else "system",
        open_mode=open_mode if open_mode in ("app", "browser") else "app",
        preferred_port=_int(get("preferred_port"), 18765, 1024, 65535),
        show_demo_model=bool(get("show_demo_model")),
        limits=SettingsLimits(
            max_concurrency=MAX_CONCURRENCY,
            max_rows_per_source=MAX_ROWS_PER_SOURCE,
            max_upload_bytes=MAX_UPLOAD_BYTES,
        ),
    )


async def load_settings(session: AsyncSession) -> Settings:
    return build_settings(await settings_repo.load_all(session))


async def get_settings(db: Database) -> Settings:
    async with db.session() as session:
        return await load_settings(session)


async def update_settings(db: Database, patch: SettingsPatch) -> Settings:
    fields = patch.model_fields_set
    changes: dict[str, Any] = {}

    if "default_concurrency" in fields and patch.default_concurrency is not None:
        sub = patch.default_concurrency
        for task in TASK_TYPES:
            value = getattr(sub, task)
            if task in sub.model_fields_set and value is not None:
                changes[f"default_concurrency.{task}"] = value
    if "default_limit" in fields:
        changes["default_limit"] = patch.default_limit
    for key in ("default_max_retries", "default_dedupe", "theme", "open_mode", "preferred_port", "show_demo_model"):
        value = getattr(patch, key)
        if key in fields and value is not None:
            changes[key] = value

    async with db.session() as session, session.begin():
        if "default_model_id" in fields and patch.default_model_id is not None:
            sub = patch.default_model_id
            for task in TASK_TYPES:
                if task not in sub.model_fields_set:
                    continue
                model_id = getattr(sub, task)
                if model_id is not None and await models_repo.get(session, model_id) is None:
                    raise field_error(f"default_model_id.{task}", "模型不存在")
                changes[f"default_model_id.{task}"] = model_id
        if "default_prompt_id" in fields and patch.default_prompt_id is not None:
            sub = patch.default_prompt_id
            for task in TASK_TYPES:
                prompt_id = getattr(sub, task)
                if task not in sub.model_fields_set or prompt_id is None:
                    continue
                row = await prompts_repo.get(session, prompt_id)
                if row is None or row.task_type != task:
                    raise field_error(f"default_prompt_id.{task}", "提示词不存在或任务类型不符")
                changes[f"default_prompt_id.{task}"] = prompt_id
        if changes:
            await settings_repo.set_values(session, changes)
        return await load_settings(session)
