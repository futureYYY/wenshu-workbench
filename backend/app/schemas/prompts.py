"""提示词、变量、渲染与试运行（04 第 5、6 节）。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import (
    ChatMessage,
    ClassifyResult,
    JoinMode,
    MaxOutputTokens,
    OutputMode,
    Schema,
    SummarizeResult,
    TaskType,
    Temperature,
    Usage,
    text_len,
)

TemplateSlot = Literal["system", "user", "chunk", "merge"]
PromptName = text_len(1, 40)
Description = text_len(0, 200)
VersionNote = text_len(0, 100)


class ClassifyFieldMap(Schema):
    label: str
    confidence: str | None
    reason: str | None


class SummarizeFieldMap(Schema):
    summary: str
    key_points: str | None


FieldMap = ClassifyFieldMap | SummarizeFieldMap


class PromptTemplate(Schema):
    id: int
    task_type: TaskType
    name: str
    description: str
    system_prompt: str
    user_template: str
    chunk_template: str | None
    merge_template: str | None
    output_mode: OutputMode
    field_map: FieldMap
    temperature: float | None
    max_output_tokens: int | None
    is_builtin: bool
    builtin_key: str | None
    version: int
    is_default: bool
    used_by_jobs: int
    created_at: str
    updated_at: str


class PromptTemplateList(Schema):
    items: list[PromptTemplate]


class PromptDraft(Schema):
    """试运行和渲染使用的“草稿”，不需要先保存。"""

    task_type: TaskType
    system_prompt: str
    user_template: str
    chunk_template: str | None = None
    merge_template: str | None = None
    output_mode: OutputMode
    field_map: FieldMap
    temperature: Temperature | None = None
    max_output_tokens: MaxOutputTokens | None = None


class PromptInput(PromptDraft):
    name: PromptName
    description: Description = ""
    note: VersionNote = ""


class PromptCopy(Schema):
    copy_from_id: int
    name: PromptName | None = None


class PromptVersionSummary(Schema):
    version: int
    note: str
    created_at: str


class PromptVersionList(Schema):
    items: list[PromptVersionSummary]


class PromptSnapshot(Schema):
    """03 第 4.3 节：prompt_versions.snapshot_json 与 jobs.prompt_snapshot_json 的结构。"""

    id: int
    name: str
    version: int
    task_type: TaskType
    system_prompt: str
    user_template: str
    chunk_template: str | None
    merge_template: str | None
    output_mode: OutputMode
    field_map: FieldMap
    temperature: float | None
    max_output_tokens: int | None


class PromptVersionDetail(Schema):
    version: int
    note: str
    created_at: str
    snapshot: PromptSnapshot


class PromptRestoreRequest(Schema):
    version: int


class PromptVariable(Schema):
    name: str
    insert: str
    description: str
    templates: list[TemplateSlot]


class PromptVariableList(Schema):
    items: list[PromptVariable]


class SampleText(Schema):
    kind: Literal["text"]
    text: str


class SampleRow(Schema):
    kind: Literal["row"]
    file_id: int
    sheet: str | None
    header_row: int
    text_columns: list[str]
    join_mode: JoinMode
    row_number: int


Sample = Annotated[SampleText | SampleRow, Field(discriminator="kind")]


class RenderRequest(Schema):
    prompt: PromptDraft
    sample: Sample
    stage: Literal["main", "chunk", "merge"] = "main"


class RenderResult(Schema):
    messages: list[ChatMessage]
    unknown_variables: list[str]
    estimated_input_tokens: int


class PlaygroundRunRequest(Schema):
    prompt: PromptDraft
    model_id: int
    sample: Sample


# ---- 试运行流的事件数据（POST /api/playground/run，text/event-stream） ----


class PlaygroundStageEvent(Schema):
    name: Literal["request", "chunk", "merge"]
    index: int | None = None
    total: int | None = None


class PlaygroundDeltaEvent(Schema):
    """delta 和 reasoning_delta 共用。"""

    content: str


class PlaygroundErrorEvent(Schema):
    error_code: str
    message: str
    status_code: int | None


class PlaygroundDone(Schema):
    raw_output: str
    reasoning: str | None
    parsed: ClassifyResult | SummarizeResult | None
    parse_error: str | None
    usage: Usage
    latency_ms: int
    chunk_count: int
    truncated: bool
    messages: list[ChatMessage]
