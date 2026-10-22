"""模型配置的业务规则（04 第 4 节、05 第 9 节、03 第 5 节“默认模型的自动切换”）。

另有一项文档之外、按使用者要求增加的初始化：首次启动时准备一条“默认自定义模型”——
从本机配置文件（WENSHU_MODELS_FILE，默认 backend/models.local.json）导入；没有配置文件时生成一条
已停用的占位条目，编辑填入真实地址后自动启用。配置文件不在 data 目录里，也不提交。
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError, conflict, not_found
from app.config import DEMO_BASE_URL, PLACEHOLDER_BASE_URL, PLACEHOLDER_MODEL
from app.db.engine import Database
from app.db.models import ModelConfigRow
from app.db.repo import models as models_repo
from app.db.repo import settings as settings_repo
from app.schemas.models import (
    LastTest,
    ModelConfig,
    ModelConfigInput,
    ModelConfigPatch,
    ModelDraftRequest,
    ModelTestResult,
    RemoteModelList,
)
from app.services.crypto import Crypto, last4, mask
from app.services.defaults import DEMO_MODEL_DEFAULTS, PLACEHOLDER_MODEL_NOTES
from app.services.llm_client import LLMClients, LLMError, ModelSpec
from app.services.output_parser import strip_reasoning
from app.utils import dumps, loads

logger = logging.getLogger(__name__)

TASK_TYPES = ("classify", "summarize")
DEMO_EDITABLE = frozenset(
    {"name", "temperature", "max_output_tokens", "context_window", "concurrency_cap", "enabled", "notes"}
)
_SIMPLE_FIELDS = (
    "name",
    "base_url",
    "model",
    "temperature",
    "max_output_tokens",
    "max_tokens_param",
    "context_window",
    "timeout_s",
    "concurrency_cap",
    "json_mode",
    "verify_ssl",
    "enabled",
    "notes",
)
PLACEHOLDER_NAME = "自定义模型"
UNSUPPORTED_LIST_MESSAGE = "这个接口不支持获取模型列表，请手动填写模型名"


# ---- 转换 ----


def is_placeholder(row: ModelConfigRow) -> bool:
    return row.provider_kind != "demo" and row.base_url == PLACEHOLDER_BASE_URL and not row.api_key_enc


def is_real(row: ModelConfigRow) -> bool:
    return row.provider_kind != "demo" and not is_placeholder(row)


def row_to_spec(row: ModelConfigRow, crypto: Crypto) -> ModelSpec:
    return ModelSpec(
        id=row.id,
        name=row.name,
        provider_kind=row.provider_kind,
        base_url=row.base_url,
        api_key=crypto.decrypt(row.api_key_enc),
        model=row.model,
        temperature=float(row.temperature),
        max_output_tokens=int(row.max_output_tokens),
        max_tokens_param=row.max_tokens_param,
        context_window=int(row.context_window),
        timeout_s=int(row.timeout_s),
        concurrency_cap=int(row.concurrency_cap),
        json_mode=bool(row.json_mode),
        verify_ssl=bool(row.verify_ssl),
        proxy_url=row.proxy_url,
        extra_headers=loads(row.extra_headers_json, {}) or {},
        extra_body=loads(row.extra_body_json, {}) or {},
        updated_at=row.updated_at,
    )


def snapshot_of(row: ModelConfigRow) -> dict[str, Any]:
    """jobs.model_snapshot_json：除密钥、测试结果、时间戳外的全部字段（03 第 4.3 节）。"""
    return {
        "id": row.id,
        "name": row.name,
        "provider_kind": row.provider_kind,
        "base_url": row.base_url,
        "model": row.model,
        "temperature": row.temperature,
        "max_output_tokens": row.max_output_tokens,
        "max_tokens_param": row.max_tokens_param,
        "context_window": row.context_window,
        "timeout_s": row.timeout_s,
        "concurrency_cap": row.concurrency_cap,
        "json_mode": bool(row.json_mode),
        "verify_ssl": bool(row.verify_ssl),
        "proxy_url": row.proxy_url,
        "extra_headers": loads(row.extra_headers_json, {}) or {},
        "extra_body": loads(row.extra_body_json, {}) or {},
    }


def to_schema(row: ModelConfigRow, crypto: Crypto, defaults: dict[str, Any], active: dict[int, int]) -> ModelConfig:
    demo = row.provider_kind == "demo"
    plain = crypto.decrypt(row.api_key_enc) if row.api_key_enc else None
    last_test = None
    if row.last_test_at:
        last_test = LastTest(
            at=row.last_test_at,
            ok=bool(row.last_test_ok),
            latency_ms=row.last_test_latency_ms,
            message=row.last_test_message or "",
        )
    return ModelConfig(
        id=row.id,
        name=row.name,
        provider_kind="demo" if demo else "openai_compatible",
        base_url=row.base_url,
        request_url="本机模拟" if demo else f"{row.base_url}/chat/completions",
        has_api_key=bool(row.api_key_enc),
        api_key_masked=mask(plain, row.api_key_last4) if row.api_key_enc else None,
        model=row.model,
        temperature=float(row.temperature),
        max_output_tokens=int(row.max_output_tokens),
        max_tokens_param="max_completion_tokens" if row.max_tokens_param == "max_completion_tokens" else "max_tokens",
        context_window=int(row.context_window),
        timeout_s=int(row.timeout_s),
        concurrency_cap=int(row.concurrency_cap),
        json_mode=bool(row.json_mode),
        verify_ssl=bool(row.verify_ssl),
        proxy_url=row.proxy_url,
        extra_headers={str(k): str(v) for k, v in (loads(row.extra_headers_json, {}) or {}).items()},
        extra_body=loads(row.extra_body_json, {}) or {},
        enabled=bool(row.enabled),
        notes=row.notes or "",
        default_for=[t for t in TASK_TYPES if defaults.get(f"default_model_id.{t}") == row.id],
        last_test=last_test,
        avg_latency_ms=row.avg_latency_ms,
        active_job_count=active.get(row.id, 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _schema_for(session: AsyncSession, crypto: Crypto, row: ModelConfigRow) -> ModelConfig:
    defaults = await settings_repo.load_all(session)
    active = await models_repo.active_job_counts(session)
    return to_schema(row, crypto, defaults, active)


# ---- 查询 ----


async def list_models(db: Database, crypto: Crypto, include_demo: bool) -> list[ModelConfig]:
    async with db.session() as session:
        values = await settings_repo.load_all(session)
        show_demo = include_demo or bool(values.get("show_demo_model", True))
        active = await models_repo.active_job_counts(session)
        rows = await models_repo.list_all(session)
        return [to_schema(r, crypto, values, active) for r in rows if show_demo or r.provider_kind != "demo"]


async def get_model(db: Database, crypto: Crypto, model_id: int) -> ModelConfig:
    async with db.session() as session:
        row = await models_repo.get(session, model_id)
        if row is None:
            raise not_found("模型不存在")
        return await _schema_for(session, crypto, row)


async def load_spec(db: Database, crypto: Crypto, model_id: int) -> tuple[ModelConfigRow, ModelSpec]:
    async with db.session() as session:
        row = await models_repo.get(session, model_id)
        if row is None:
            raise not_found("模型不存在")
        return row, row_to_spec(row, crypto)


# ---- 默认模型的自动切换 ----


async def _maybe_switch_defaults(session: AsyncSession, row: ModelConfigRow) -> bool:
    """第一个真实模型出现时，若两个默认模型设置仍指向演示模型，就都改成它。"""
    if not is_real(row) or not row.enabled:
        return False
    demo = await models_repo.get_demo(session)
    if demo is None:
        return False
    values = await settings_repo.load_all(session)
    if any(values.get(f"default_model_id.{t}") != demo.id for t in TASK_TYPES):
        return False
    others = [r for r in await models_repo.list_all(session) if r.id != row.id and is_real(r)]
    if others:
        return False
    await settings_repo.set_values(session, {f"default_model_id.{t}": row.id for t in TASK_TYPES})
    logger.info("第一个真实模型“%s”已设为意图识别和文本摘要的默认模型", row.name)
    return True


# ---- 新建、修改、删除 ----


def _key_fields(crypto: Crypto, api_key: str | None) -> dict[str, Any]:
    key = (api_key or "").strip()
    if not key:
        return {"api_key_enc": None, "api_key_last4": None}
    return {"api_key_enc": crypto.encrypt(key), "api_key_last4": last4(key)}


def _input_fields(payload: ModelConfigInput) -> dict[str, Any]:
    return {
        "name": payload.name,
        "base_url": payload.base_url,
        "model": payload.model,
        "temperature": payload.temperature,
        "max_output_tokens": payload.max_output_tokens,
        "max_tokens_param": payload.max_tokens_param,
        "context_window": payload.context_window,
        "timeout_s": payload.timeout_s,
        "concurrency_cap": payload.concurrency_cap,
        "json_mode": payload.json_mode,
        "verify_ssl": payload.verify_ssl,
        "proxy_url": payload.proxy_url,
        "extra_headers_json": dumps(payload.extra_headers),
        "extra_body_json": dumps(payload.extra_body),
        "enabled": payload.enabled,
        "notes": payload.notes,
    }


async def create_model(db: Database, crypto: Crypto, payload: ModelConfigInput) -> ModelConfig:
    async with db.session() as session, session.begin():
        if await models_repo.get_by_name(session, payload.name):
            raise conflict("MODEL_NAME_TAKEN", f"模型名称“{payload.name}”已被使用")
        row = await models_repo.insert(
            session,
            provider_kind="openai_compatible",
            **_input_fields(payload),
            **_key_fields(crypto, payload.api_key),
        )
        await _maybe_switch_defaults(session, row)
        return await _schema_for(session, crypto, row)


def _current_value(row: ModelConfigRow, field: str) -> Any:
    if field == "extra_headers":
        return loads(row.extra_headers_json, {})
    if field == "extra_body":
        return loads(row.extra_body_json, {})
    if field == "api_key":
        return None
    return getattr(row, field)


async def update_model(db: Database, crypto: Crypto, model_id: int, patch: ModelConfigPatch) -> ModelConfig:
    provided = patch.model_fields_set
    async with db.session() as session, session.begin():
        row = await models_repo.get(session, model_id)
        if row is None:
            raise not_found("模型不存在")
        if row.provider_kind == "demo":
            for field in provided - DEMO_EDITABLE:
                value = getattr(patch, field)
                if field == "api_key":
                    if (value or "").strip():
                        raise conflict("DEMO_MODEL_PROTECTED", "演示模型不需要密钥，也不能修改接口地址等固定字段")
                    continue
                if value is not None and value != _current_value(row, field):
                    raise conflict(
                        "DEMO_MODEL_PROTECTED",
                        "演示模型只能修改名称、温度、最大输出、上下文长度、并发上限、启用状态和备注",
                    )
        was_placeholder = is_placeholder(row)
        changes: dict[str, Any] = {}
        for field in _SIMPLE_FIELDS:
            value = getattr(patch, field)
            if field in provided and value is not None:
                if row.provider_kind == "demo" and field not in DEMO_EDITABLE:
                    continue
                changes[field] = value
        if "name" in changes and changes["name"] != row.name:
            other = await models_repo.get_by_name(session, changes["name"])
            if other is not None and other.id != row.id:
                raise conflict("MODEL_NAME_TAKEN", f"模型名称“{changes['name']}”已被使用")
        if row.provider_kind != "demo":
            if "proxy_url" in provided:
                changes["proxy_url"] = patch.proxy_url
            if "extra_headers" in provided and patch.extra_headers is not None:
                changes["extra_headers_json"] = dumps(patch.extra_headers)
            if "extra_body" in provided and patch.extra_body is not None:
                changes["extra_body_json"] = dumps(patch.extra_body)
            if "api_key" in provided:
                # 04 第 4 节：null 清除；空字符串等同于不传（不改）；非空字符串替换
                if patch.api_key is None:
                    changes.update(_key_fields(crypto, None))
                elif patch.api_key.strip():
                    changes.update(_key_fields(crypto, patch.api_key))
        if (
            was_placeholder
            and "enabled" not in provided
            and changes.get("base_url", row.base_url) != PLACEHOLDER_BASE_URL
        ):
            changes["enabled"] = True   # 占位条目填入真实地址后自动启用
        await models_repo.update_fields(session, row, changes)
        if was_placeholder:
            # 占位条目被填成真实模型，相当于“创建了第一个真实模型”；修改其他模型不改默认设置
            await _maybe_switch_defaults(session, row)
        return await _schema_for(session, crypto, row)


async def delete_model(db: Database, model_id: int) -> None:
    async with db.session() as session, session.begin():
        row = await models_repo.get(session, model_id)
        if row is None:
            raise not_found("模型不存在")
        if row.provider_kind == "demo":
            raise conflict("DEMO_MODEL_PROTECTED", "演示模型不能删除，可以在设置里隐藏")
        active = (await models_repo.active_job_counts(session)).get(model_id, 0)
        if active:
            raise conflict("MODEL_IN_USE", f"还有 {active} 个排队、运行中或已暂停的任务在使用这个模型，先取消或删除它们")
        values = await settings_repo.load_all(session)
        cleared = {
            f"default_model_id.{t}": None for t in TASK_TYPES if values.get(f"default_model_id.{t}") == model_id
        }
        if cleared:
            await settings_repo.set_values(session, cleared)
        await models_repo.delete_model(session, model_id)


# ---- 测试连接与获取模型列表（05 第 9 节） ----


async def run_test(llm: LLMClients, spec: ModelSpec) -> ModelTestResult:
    # 05 第 9 节：测试连接不发 response_format。JSON 模式只在正式请求里生效；
    # 额外请求体里写了 response_format 的也去掉，否则要求提示词含“json”的上游（如 DeepSeek）会直接 400
    spec = replace(
        spec, json_mode=False, extra_body={k: v for k, v in (spec.extra_body or {}).items() if k != "response_format"}
    )
    try:
        result = await llm.chat(
            spec,
            [{"role": "user", "content": "请只回复：OK"}],
            temperature=spec.temperature,
            max_tokens=32,
            json_output=False,
            timeout=float(min(spec.timeout_s, 30)),
        )
    except LLMError as err:
        message = err.message
        if err.error_code == "MODEL_NOT_FOUND" and not spec.is_demo and "/v1" not in spec.base_url:
            message += "；地址可能少了 /v1"
        return ModelTestResult(
            ok=False,
            latency_ms=err.latency_ms,
            status_code=err.status_code,
            error_code=err.error_code,
            message=message,
            sample_output=None,
        )
    if not result.has_choices:
        return ModelTestResult(
            ok=False,
            latency_ms=result.latency_ms,
            status_code=200,
            error_code="EMPTY_OUTPUT",
            message="返回内容里没有 choices，接口可能不兼容 OpenAI 格式",
            sample_output=None,
        )
    content, _reasoning = strip_reasoning(result.content, result.reasoning)
    message = "连接正常"
    if not content.strip():
        message += "，但模型返回了空内容（会思考的模型可能需要更大的最大输出）"
    return ModelTestResult(
        ok=True,
        latency_ms=result.latency_ms,
        status_code=200,
        error_code=None,
        message=message,
        sample_output=content.strip()[:100] or None,
    )


async def test_saved(db: Database, crypto: Crypto, llm: LLMClients, model_id: int) -> ModelTestResult:
    _row, spec = await load_spec(db, crypto, model_id)
    result = await run_test(llm, spec)
    async with db.session() as session, session.begin():
        await models_repo.record_test(
            session, model_id, ok=result.ok, latency_ms=result.latency_ms, message=result.message
        )
    return result


async def draft_spec(db: Database, crypto: Crypto, req: ModelDraftRequest) -> ModelSpec:
    cfg = req.config
    raw = cfg.api_key
    api_key: str | None = None
    if raw is not None and raw.strip():
        api_key = raw                      # 非空字符串：用这个值
    elif raw is None and "api_key" in cfg.model_fields_set:
        api_key = None                     # 显式 null：无密钥
    elif req.model_id is not None:
        # 不传或空字符串：用 model_id 已保存的密钥
        async with db.session() as session:
            row = await models_repo.get(session, req.model_id)
            if row is not None and row.api_key_enc:
                api_key = crypto.decrypt(row.api_key_enc)
    return ModelSpec(
        id=None,
        name=cfg.name,
        provider_kind="openai_compatible",
        base_url=cfg.base_url,
        api_key=(api_key or "").strip() or None,
        model=cfg.model,
        temperature=cfg.temperature,
        max_output_tokens=cfg.max_output_tokens,
        max_tokens_param=cfg.max_tokens_param,
        context_window=cfg.context_window,
        timeout_s=cfg.timeout_s,
        concurrency_cap=cfg.concurrency_cap,
        json_mode=cfg.json_mode,
        verify_ssl=cfg.verify_ssl,
        proxy_url=cfg.proxy_url,
        extra_headers=dict(cfg.extra_headers),
        extra_body=dict(cfg.extra_body),
    )


async def test_draft(db: Database, crypto: Crypto, llm: LLMClients, req: ModelDraftRequest) -> ModelTestResult:
    return await run_test(llm, await draft_spec(db, crypto, req))


async def list_remote(db: Database, crypto: Crypto, llm: LLMClients, req: ModelDraftRequest) -> RemoteModelList:
    spec = await draft_spec(db, crypto, req)
    try:
        models = await llm.list_models(spec)
    except LLMError as err:
        unsupported = err.error_code in ("BAD_RESPONSE", "MODEL_NOT_FOUND") or err.status_code == 405
        message = UNSUPPORTED_LIST_MESSAGE if unsupported else err.message
        raise AppError(
            502, "UPSTREAM_ERROR", message, {"status_code": err.status_code, "error_code": err.error_code}
        ) from err
    return RemoteModelList(models=models)


# ---- 启动初始化：演示模型与默认自定义模型 ----


async def ensure_demo_model(session: AsyncSession) -> ModelConfigRow:
    demo = await models_repo.get_demo(session)
    if demo is not None:
        return demo
    name = DEMO_MODEL_DEFAULTS["name"]
    if await models_repo.get_by_name(session, name):
        name = f"{name}（内置）"
    return await models_repo.insert(
        session,
        name=name,
        provider_kind="demo",
        base_url=DEMO_BASE_URL,
        model=DEMO_MODEL_DEFAULTS["model"],
        context_window=DEMO_MODEL_DEFAULTS["context_window"],
        notes=DEMO_MODEL_DEFAULTS["notes"],
        api_key_enc=None,
        api_key_last4=None,
    )


def _read_local_entries(path: Path) -> list[ModelConfigInput]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        logger.warning("本机模型配置 %s 读取失败：%s", path, exc)
        return []
    raw_entries = data if isinstance(data, list) else [data]
    entries: list[ModelConfigInput] = []
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict):
            continue
        try:
            entries.append(ModelConfigInput.model_validate(raw))
        except ValidationError as exc:
            fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
            logger.warning("本机模型配置第 %d 项无效（%s），已跳过", index, fields)
    return entries


async def prepare_custom_model(session: AsyncSession, crypto: Crypto, models_file: Path, fresh_db: bool) -> None:
    """导入本机配置里尚不存在的模型；首次建库且没有任何非演示模型时生成占位条目。"""
    for entry in _read_local_entries(models_file):
        if await models_repo.get_by_name(session, entry.name):
            continue
        rows = await models_repo.list_all(session)
        placeholder = next((r for r in rows if is_placeholder(r)), None)
        fields = {**_input_fields(entry), **_key_fields(crypto, entry.api_key)}
        if placeholder is not None:
            await models_repo.update_fields(session, placeholder, fields)
            row = placeholder
        else:
            row = await models_repo.insert(session, provider_kind="openai_compatible", **fields)
        logger.info("已从本机配置导入模型“%s”", entry.name)
        await _maybe_switch_defaults(session, row)

    if fresh_db:
        count = (
            await session.execute(
                select(func.count()).select_from(ModelConfigRow).where(ModelConfigRow.provider_kind != "demo")
            )
        ).scalar_one()
        if not count:
            name = PLACEHOLDER_NAME
            if await models_repo.get_by_name(session, name):
                name = f"{PLACEHOLDER_NAME} 1"
            await models_repo.insert(
                session,
                name=name,
                provider_kind="openai_compatible",
                base_url=PLACEHOLDER_BASE_URL,
                model=PLACEHOLDER_MODEL,
                enabled=False,
                notes=PLACEHOLDER_MODEL_NOTES,
                api_key_enc=None,
                api_key_last4=None,
            )
            logger.info("已生成默认自定义模型的占位条目，可在模型页编辑")
