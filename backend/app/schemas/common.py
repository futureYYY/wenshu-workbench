"""共用的类型、校验器和小模型（04 第 1 节）。

约定：
- 响应模型的字段一律没有默认值（OpenAPI 中都是必填，前端类型不会出现可选字段）；
- 请求模型用默认值表示“可以不传”，PATCH 用 model_fields_set 区分“不传”和“传 null”；
- 校验失败的说明直接写成中文，统一错误处理把它们放进 detail.fields。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic_core import PydanticCustomError

TaskType = Literal["classify", "summarize"]
JobStatus = Literal["queued", "running", "paused", "completed", "cancelled"]
# 暂停原因码（03 第 6.1 节）；界面按它决定提示和操作
StatusReasonCode = Literal["user_pause", "shutdown", "auth_failed", "model_not_found", "circuit_breaker", "write_failed"]
ItemStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
JoinMode = Literal["labeled", "plain"]
OutputMode = Literal["json", "text"]

TASK_TYPE_LABELS: dict[str, str] = {"classify": "意图识别", "summarize": "文本摘要"}


class Schema(BaseModel):
    # model_id、model_name 等字段名与 Pydantic 的保护前缀无关，关闭检查
    model_config = ConfigDict(protected_namespaces=())


def int_range(lo: int, hi: int) -> Any:
    def check(value: int) -> int:
        if value < lo or value > hi:
            raise PydanticCustomError("range", "必须在 {lo} 到 {hi} 之间", {"lo": lo, "hi": hi})
        return value

    return Annotated[int, AfterValidator(check), Field(json_schema_extra={"minimum": lo, "maximum": hi})]


def float_range(lo: float, hi: float) -> Any:
    def check(value: float) -> float:
        if value < lo or value > hi:
            raise PydanticCustomError("range", "必须在 {lo} 到 {hi} 之间", {"lo": _fmt(lo), "hi": _fmt(hi)})
        return value

    return Annotated[float, AfterValidator(check), Field(json_schema_extra={"minimum": lo, "maximum": hi})]


def text_len(lo: int, hi: int, *, strip: bool = True) -> Any:
    def check(value: str) -> str:
        if strip:
            value = value.strip()
        if len(value) < lo:
            if lo == 1:
                raise PydanticCustomError("text_empty", "不能为空")
            raise PydanticCustomError("text_short", "至少 {lo} 个字", {"lo": lo})
        if len(value) > hi:
            raise PydanticCustomError("text_long", "不能超过 {hi} 个字", {"hi": hi})
        return value

    return Annotated[str, AfterValidator(check), Field(json_schema_extra={"minLength": lo, "maxLength": hi})]


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _non_empty_list(value: list[str]) -> list[str]:
    cleaned = [v for v in value if isinstance(v, str) and v != ""]
    if not cleaned:
        raise PydanticCustomError("list_empty", "至少选择 1 项")
    return cleaned


# 常用的受限类型
Concurrency = int_range(1, 20)
Retries = int_range(0, 5)
RowLimit = int_range(1, 100_000)
Temperature = float_range(0, 2)
MaxOutputTokens = int_range(16, 32_768)
ContextWindow = int_range(1024, 2_000_000)
TimeoutSeconds = int_range(5, 600)
Port = int_range(1024, 65_535)
NonEmptyStrList = Annotated[list[str], AfterValidator(_non_empty_list)]


class ChatMessage(Schema):
    role: Literal["system", "user", "assistant"]
    content: str


class ClassifyResult(Schema):
    label: str
    confidence: float | None
    reason: str | None


class KeyPoint(Schema):
    text: str
    sources: list[int]


class SummarizeResult(Schema):
    summary: str
    key_points: list[KeyPoint]


class Usage(Schema):
    prompt_tokens: int
    completion_tokens: int


class ErrorBody(Schema):
    code: str
    message: str
    detail: dict[str, Any]


class ErrorResponse(Schema):
    error: ErrorBody
