"""提示词模板的业务规则（04 第 5 节、05 第 2、3 节）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError

from app.api.errors import AppError, bad_request, conflict, field_error, not_found, unprocessable
from app.context import AppContext
from app.db.engine import Database
from app.db.models import PromptTemplateRow
from app.db.repo import prompts as prompts_repo
from app.db.repo import settings as settings_repo
from app.schemas.common import ChatMessage
from app.schemas.prompts import (
    ClassifyFieldMap,
    PromptCopy,
    PromptDraft,
    PromptInput,
    PromptSnapshot,
    PromptTemplate,
    PromptVariable,
    PromptVersionDetail,
    PromptVersionSummary,
    RenderRequest,
    RenderResult,
    SampleRow,
    SampleText,
    SummarizeFieldMap,
)
from app.services import file_service, segmenter
from app.services.defaults import BUILTIN_KEY_BY_TASK, BUILTIN_PROMPTS
from app.services.file_parser import TEXT_KEY, TEXT_TITLE
from app.services.prompt_render import (
    PromptSpec,
    RowContext,
    StageVars,
    assemble,
    has_required_input,
    referenced_names,
    summarize_main_stage,
    variables_for,
)
from app.utils import dumps, loads

SAMPLE_FILE_NAME = "试运行样本"
INPUT_VARIABLE_MESSAGE = "用户消息模板至少要引用 {{text}}、{{text_numbered}}、{{row_json}} 或 {{col:列名}} 之一"


# ---- 转换 ----


def field_map_for(task_type: str, data: dict[str, Any]) -> ClassifyFieldMap | SummarizeFieldMap:
    if task_type == "summarize":
        return SummarizeFieldMap(summary=str(data.get("summary") or ""), key_points=data.get("key_points"))
    return ClassifyFieldMap(label=str(data.get("label") or ""), confidence=data.get("confidence"), reason=data.get("reason"))


def to_schema(row: PromptTemplateRow, settings: dict[str, Any], used: dict[int, int]) -> PromptTemplate:
    return PromptTemplate(
        id=row.id,
        task_type=row.task_type,  # type: ignore[arg-type]
        name=row.name,
        description=row.description or "",
        system_prompt=row.system_prompt,
        user_template=row.user_template,
        chunk_template=row.chunk_template,
        merge_template=row.merge_template,
        output_mode="text" if row.output_mode == "text" else "json",
        field_map=field_map_for(row.task_type, loads(row.field_map_json, {}) or {}),
        temperature=row.temperature,
        max_output_tokens=row.max_output_tokens,
        is_builtin=bool(row.is_builtin),
        builtin_key=row.builtin_key,
        version=row.version,
        is_default=settings.get(f"default_prompt_id.{row.task_type}") == row.id,
        used_by_jobs=used.get(row.id, 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def snapshot_model(data: dict[str, Any]) -> PromptSnapshot:
    task_type = str(data.get("task_type") or "classify")
    return PromptSnapshot(
        id=int(data.get("id") or 0),
        name=str(data.get("name") or ""),
        version=int(data.get("version") or 1),
        task_type=task_type,  # type: ignore[arg-type]
        system_prompt=str(data.get("system_prompt") or ""),
        user_template=str(data.get("user_template") or ""),
        chunk_template=data.get("chunk_template"),
        merge_template=data.get("merge_template"),
        output_mode="text" if data.get("output_mode") == "text" else "json",
        field_map=field_map_for(task_type, data.get("field_map") or {}),
        temperature=data.get("temperature"),
        max_output_tokens=data.get("max_output_tokens"),
    )


def spec_from_draft(draft: PromptDraft) -> PromptSpec:
    return PromptSpec(
        task_type=draft.task_type,
        system_prompt=draft.system_prompt,
        user_template=draft.user_template,
        chunk_template=draft.chunk_template if draft.task_type == "summarize" else None,
        merge_template=draft.merge_template if draft.task_type == "summarize" else None,
        output_mode=draft.output_mode,
        field_map=draft.field_map.model_dump(),
        temperature=draft.temperature,
        max_output_tokens=draft.max_output_tokens,
    )


# ---- 保存时的校验（04 第 5 节） ----


def validate_draft(draft: PromptDraft) -> None:
    if not has_required_input(draft.user_template):
        raise unprocessable("PROMPT_NO_INPUT_VARIABLE", INPUT_VARIABLE_MESSAGE)
    if draft.task_type == "summarize":
        chunk = (draft.chunk_template or "").strip()
        merge = (draft.merge_template or "").strip()
        if not chunk or not merge:
            raise unprocessable("PROMPT_TEMPLATE_MISSING", "摘要模板需要分段模板和合并模板（在“长文本分段”里）")
        if not referenced_names(chunk) & {"text", "text_numbered"}:
            raise unprocessable("PROMPT_TEMPLATE_MISSING", "分段模板必须包含 {{text}} 或 {{text_numbered}}")
        if "chunk_summaries" not in referenced_names(merge):
            raise unprocessable("PROMPT_TEMPLATE_MISSING", "合并模板必须包含 {{chunk_summaries}}")
    field_map = draft.field_map
    if draft.task_type == "classify" and not isinstance(field_map, ClassifyFieldMap):
        raise field_error("field_map", "意图识别的输出字段映射需要 label、confidence、reason")
    if draft.task_type == "summarize" and not isinstance(field_map, SummarizeFieldMap):
        raise field_error("field_map", "文本摘要的输出字段映射需要 summary、key_points")
    if draft.output_mode == "json":
        if isinstance(field_map, ClassifyFieldMap) and not field_map.label.strip():
            raise field_error("field_map.label", "JSON 模式下必须填写类别字段名")
        if isinstance(field_map, SummarizeFieldMap) and not field_map.summary.strip():
            raise field_error("field_map.summary", "JSON 模式下必须填写摘要字段名")


def _content_fields(draft: PromptDraft) -> dict[str, Any]:
    summarize = draft.task_type == "summarize"
    return {
        "system_prompt": draft.system_prompt,
        "user_template": draft.user_template,
        "chunk_template": draft.chunk_template if summarize else None,
        "merge_template": draft.merge_template if summarize else None,
        "output_mode": draft.output_mode,
        "field_map_json": dumps(_clean_field_map(draft.field_map.model_dump())),
        "temperature": draft.temperature,
        "max_output_tokens": draft.max_output_tokens,
    }


def _clean_field_map(data: dict[str, Any]) -> dict[str, Any]:
    """label、summary 保留为字符串（可为空串，纯文本模式不用）；其余字段名为空时存 null。"""
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        text = value.strip() if isinstance(value, str) else value
        cleaned[key] = (text or "") if key in ("label", "summary") else (text or None)
    return cleaned


def _row_content(row: PromptTemplateRow) -> dict[str, Any]:
    return {
        "system_prompt": row.system_prompt,
        "user_template": row.user_template,
        "chunk_template": row.chunk_template,
        "merge_template": row.merge_template,
        "output_mode": row.output_mode,
        "field_map_json": dumps(loads(row.field_map_json, {}) or {}),
        "temperature": row.temperature,
        "max_output_tokens": row.max_output_tokens,
    }


# ---- 查询 ----


async def _context(session: Any) -> tuple[dict[str, Any], dict[int, int]]:
    return await settings_repo.load_all(session), await prompts_repo.used_by_jobs(session)


async def list_prompts(db: Database, task_type: str | None) -> list[PromptTemplate]:
    async with db.session() as session:
        settings, used = await _context(session)
        rows = await prompts_repo.list_templates(session, task_type)
    items = [to_schema(r, settings, used) for r in rows]
    type_order = {"classify": 0, "summarize": 1}
    # 默认模板在最前，其次内置，其余按修改时间倒序（排序是稳定的，先按时间倒序再按优先级）
    items.sort(key=lambda p: p.updated_at, reverse=True)
    items.sort(key=lambda p: (type_order.get(p.task_type, 9), 0 if p.is_default else 1, 0 if p.is_builtin else 1))
    return items


async def get_prompt(db: Database, prompt_id: int) -> PromptTemplate:
    async with db.session() as session:
        row = await prompts_repo.get(session, prompt_id)
        if row is None:
            raise not_found("提示词不存在")
        settings, used = await _context(session)
        return to_schema(row, settings, used)


async def _require(session: Any, prompt_id: int) -> PromptTemplateRow:
    row = await prompts_repo.get(session, prompt_id)
    if row is None:
        raise not_found("提示词不存在")
    return row


# ---- 新建、保存、删除 ----


async def create_prompt(db: Database, body: PromptInput | PromptCopy) -> PromptTemplate:
    try:
        async with db.session() as session, session.begin():
            if isinstance(body, PromptCopy):
                source = await _require(session, body.copy_from_id)
                if body.name:
                    name = body.name
                    if await prompts_repo.get_by_name(session, source.task_type, name):
                        raise conflict("PROMPT_NAME_TAKEN", f"同一任务类型下已有名为“{name}”的提示词")
                else:
                    name = f"{source.name} 副本"[:40]
                    index = 2
                    while await prompts_repo.get_by_name(session, source.task_type, name):
                        name = f"{source.name} 副本 {index}"[:40]
                        index += 1
                fields = {
                    "task_type": source.task_type,
                    "name": name,
                    "description": source.description,
                    **_row_content(source),
                }
                note = f"复制自“{source.name}” v{source.version}"
            else:
                validate_draft(body)
                if await prompts_repo.get_by_name(session, body.task_type, body.name):
                    raise conflict("PROMPT_NAME_TAKEN", f"同一任务类型下已有名为“{body.name}”的提示词")
                fields = {
                    "task_type": body.task_type,
                    "name": body.name,
                    "description": body.description,
                    **_content_fields(body),
                }
                note = body.note
            row = await prompts_repo.insert(session, is_builtin=False, builtin_key=None, version=1, **fields)
            await prompts_repo.add_version(session, row.id, 1, prompts_repo.snapshot_of(row), note)
            settings, used = await _context(session)
            return to_schema(row, settings, used)
    except IntegrityError as exc:
        raise conflict("PROMPT_NAME_TAKEN", "同一任务类型下已有同名的提示词") from exc


async def save_prompt(db: Database, prompt_id: int, body: PromptInput) -> PromptTemplate:
    async with db.session() as session, session.begin():
        row = await _require(session, prompt_id)
        if body.task_type != row.task_type:
            raise field_error("task_type", "任务类型不能修改")
        validate_draft(body)
        if body.name != row.name:
            other = await prompts_repo.get_by_name(session, row.task_type, body.name)
            if other is not None and other.id != row.id:
                raise conflict("PROMPT_NAME_TAKEN", f"同一任务类型下已有名为“{body.name}”的提示词")
        content = _content_fields(body)
        changed = content != _row_content(row)
        fields: dict[str, Any] = {"name": body.name, "description": body.description}
        if changed:
            fields.update(content)
            fields["version"] = row.version + 1
        await prompts_repo.update_fields(session, row, fields)
        if changed:
            await prompts_repo.add_version(session, row.id, row.version, prompts_repo.snapshot_of(row), body.note)
        settings, used = await _context(session)
        return to_schema(row, settings, used)


async def delete_prompt(db: Database, prompt_id: int) -> None:
    async with db.session() as session, session.begin():
        row = await _require(session, prompt_id)
        if row.is_builtin:
            raise conflict("PROMPT_BUILTIN_PROTECTED", "内置模板不能删除，可以恢复内置默认")
        settings = await settings_repo.load_all(session)
        key = f"default_prompt_id.{row.task_type}"
        if settings.get(key) == row.id:
            builtin = await prompts_repo.get_by_builtin_key(session, BUILTIN_KEY_BY_TASK[row.task_type])
            if builtin is not None:
                await settings_repo.set_values(session, {key: builtin.id})
        await prompts_repo.delete_template(session, prompt_id)


# ---- 版本 ----


async def list_versions(db: Database, prompt_id: int) -> list[PromptVersionSummary]:
    async with db.session() as session:
        await _require(session, prompt_id)
        rows = await prompts_repo.list_versions(session, prompt_id)
    return [PromptVersionSummary(version=r.version, note=r.note, created_at=r.created_at) for r in rows]


async def get_version(db: Database, prompt_id: int, version: int) -> PromptVersionDetail:
    async with db.session() as session:
        await _require(session, prompt_id)
        row = await prompts_repo.get_version(session, prompt_id, version)
    if row is None:
        raise not_found(f"版本 v{version} 不存在")
    return PromptVersionDetail(
        version=row.version,
        note=row.note,
        created_at=row.created_at,
        snapshot=snapshot_model(loads(row.snapshot_json, {}) or {}),
    )


async def _save_as_new_version(session: Any, row: PromptTemplateRow, content: dict[str, Any], note: str) -> None:
    fields = dict(content)
    fields["version"] = row.version + 1
    await prompts_repo.update_fields(session, row, fields)
    await prompts_repo.add_version(session, row.id, row.version, prompts_repo.snapshot_of(row), note)


async def restore_version(db: Database, prompt_id: int, version: int) -> PromptTemplate:
    async with db.session() as session, session.begin():
        row = await _require(session, prompt_id)
        old = await prompts_repo.get_version(session, prompt_id, version)
        if old is None:
            raise not_found(f"版本 v{version} 不存在")
        snap: dict[str, Any] = loads(old.snapshot_json, {}) or {}
        summarize = row.task_type == "summarize"
        content = {
            "system_prompt": str(snap.get("system_prompt") or ""),
            "user_template": str(snap.get("user_template") or ""),
            "chunk_template": snap.get("chunk_template") if summarize else None,
            "merge_template": snap.get("merge_template") if summarize else None,
            "output_mode": "text" if snap.get("output_mode") == "text" else "json",
            "field_map_json": dumps(snap.get("field_map") or {}),
            "temperature": snap.get("temperature"),
            "max_output_tokens": snap.get("max_output_tokens"),
        }
        await _save_as_new_version(session, row, content, f"恢复自 v{version}")
        settings, used = await _context(session)
        return to_schema(row, settings, used)


async def reset_builtin(db: Database, prompt_id: int) -> PromptTemplate:
    async with db.session() as session, session.begin():
        row = await _require(session, prompt_id)
        if not row.is_builtin or row.builtin_key not in BUILTIN_PROMPTS:
            raise bad_request("只有内置模板可以恢复内置默认")
        data = BUILTIN_PROMPTS[row.builtin_key]
        content = {
            "system_prompt": data["system_prompt"],
            "user_template": data["user_template"],
            "chunk_template": data["chunk_template"],
            "merge_template": data["merge_template"],
            "output_mode": data["output_mode"],
            "field_map_json": dumps(data["field_map"]),
            "temperature": data["temperature"],
            "max_output_tokens": data["max_output_tokens"],
        }
        await _save_as_new_version(session, row, content, "恢复内置默认")
        settings, used = await _context(session)
        return to_schema(row, settings, used)


def list_variables(task_type: str) -> list[PromptVariable]:
    return [PromptVariable(**v) for v in variables_for(task_type)]


# ---- 样本与渲染 ----


async def resolve_sample(ctx: AppContext, sample: SampleText | SampleRow) -> RowContext:
    if isinstance(sample, SampleText):
        text = sample.text.strip()
        return RowContext(
            text=text,
            row_number=1,
            file_name=SAMPLE_FILE_NAME,
            row_values={TEXT_KEY: text},
            columns=[(TEXT_KEY, TEXT_TITLE)],
        )
    if not sample.text_columns:
        raise field_error("sample.text_columns", "至少选择 1 项")
    return await file_service.sample_row(
        ctx, sample.file_id, sample.sheet, sample.header_row, sample.text_columns, sample.join_mode, sample.row_number
    )


MERGE_PREVIEW_PARTS = ["（第 1 部分的摘要）", "（第 2 部分的摘要）"]


async def render(ctx: AppContext, req: RenderRequest) -> RenderResult:
    spec = spec_from_draft(req.prompt)
    row = await resolve_sample(ctx, req.sample)
    if req.stage == "chunk":
        if spec.task_type != "summarize":
            raise bad_request("只有文本摘要有分段模板")
        segments = segmenter.split_segments(row.text)
        stage = StageVars(text=row.text, text_numbered=segmenter.numbered_text(segments), chunk_index=1, chunk_total=1)
        messages = assemble(spec, spec.chunk_template or "", row, stage, "chunk")
    elif req.stage == "merge":
        if spec.task_type != "summarize":
            raise bad_request("只有文本摘要有合并模板")
        stage = StageVars(text=row.text, chunk_summaries=segmenter.format_chunk_summaries(MERGE_PREVIEW_PARTS))
        messages = assemble(spec, spec.merge_template or "", row, stage, "merge")
    else:
        stage = summarize_main_stage(row, segmenter.split_segments(row.text))
        messages = assemble(spec, spec.user_template, row, stage, "user")
    contents = [m["content"] for m in messages.messages]
    return RenderResult(
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages.messages],  # type: ignore[arg-type]
        unknown_variables=messages.unknown,
        estimated_input_tokens=segmenter.estimate_messages_tokens(contents),
    )


def ensure_valid_for_run(spec: PromptSpec) -> None:
    if not spec.user_template.strip():
        raise AppError(422, "PROMPT_NO_INPUT_VARIABLE", INPUT_VARIABLE_MESSAGE)
