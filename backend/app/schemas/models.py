"""模型配置（04 第 4 节）。"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field
from pydantic_core import PydanticCustomError

from app.schemas.common import (
    Concurrency,
    ContextWindow,
    MaxOutputTokens,
    Schema,
    TaskType,
    Temperature,
    TimeoutSeconds,
    text_len,
)

ProviderKind = Literal["openai_compatible", "demo"]
MaxTokensParam = Literal["max_tokens", "max_completion_tokens"]


def normalize_base_url(raw: str) -> str:
    """05 第 1.2 节：去空白、去末尾 /、去 /chat/completions。不自动补 /v1。"""
    url = raw.strip().rstrip("/")
    if url.lower().endswith("/chat/completions"):
        url = url[: -len("/chat/completions")].rstrip("/")
    return url


def _check_base_url(value: str) -> str:
    url = normalize_base_url(value)
    if not url.lower().startswith(("http://", "https://")):
        raise PydanticCustomError("base_url", "必须以 http:// 或 https:// 开头")
    if len(url) > 500:
        raise PydanticCustomError("text_long", "不能超过 {hi} 个字", {"hi": 500})
    return url


def _check_proxy(value: str | None) -> str | None:
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if not url.lower().startswith(("http://", "https://")):
        raise PydanticCustomError("proxy_url", "必须以 http:// 或 https:// 开头，留空表示直连")
    return url


def _check_headers(value: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, val in value.items():
        name = str(key).strip()
        if not name:
            continue
        if any(ch in name for ch in " \t\r\n:"):
            raise PydanticCustomError("header_name", "请求头名称“{name}”不合法", {"name": name})
        cleaned[name] = str(val)
    return cleaned


BaseUrl = Annotated[str, AfterValidator(_check_base_url)]
ProxyUrl = Annotated[str | None, AfterValidator(_check_proxy)]
Headers = Annotated[dict[str, str], AfterValidator(_check_headers)]
ModelName = text_len(1, 40)
ModelIdentifier = text_len(1, 200)
Notes = text_len(0, 500)


class LastTest(Schema):
    at: str
    ok: bool
    latency_ms: int | None
    message: str


class ModelConfig(Schema):
    id: int
    name: str
    provider_kind: ProviderKind
    base_url: str
    request_url: str
    has_api_key: bool
    api_key_masked: str | None
    model: str
    temperature: float
    max_output_tokens: int
    max_tokens_param: MaxTokensParam
    context_window: int
    timeout_s: int
    concurrency_cap: int
    json_mode: bool
    verify_ssl: bool
    proxy_url: str | None
    extra_headers: dict[str, str]
    extra_body: dict[str, Any]
    enabled: bool
    notes: str
    default_for: list[TaskType]
    last_test: LastTest | None
    avg_latency_ms: int | None
    active_job_count: int
    created_at: str
    updated_at: str


class ModelConfigList(Schema):
    items: list[ModelConfig]


class ModelConfigInput(Schema):
    """POST 时 name、base_url、model 必填。api_key：不传、null 或空字符串都表示无密钥（04 第 4 节）。
    proxy_url：null 或空字符串表示直连（不使用系统代理），只支持 http:// 和 https:// 代理。"""

    name: ModelName
    base_url: BaseUrl
    api_key: str | None = None
    model: ModelIdentifier
    temperature: Temperature = 0.3
    max_output_tokens: MaxOutputTokens = 1024
    max_tokens_param: MaxTokensParam = "max_tokens"
    context_window: ContextWindow = 32768
    timeout_s: TimeoutSeconds = 120
    concurrency_cap: Concurrency = 20
    json_mode: bool = False
    verify_ssl: bool = True
    proxy_url: ProxyUrl = None
    extra_headers: Headers = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    notes: Notes = ""


class ModelConfigPatch(Schema):
    """PATCH 时全部可选。api_key：不传或空字符串表示不改（编辑表单里密钥框留空时不会误删）；
    显式传 null 表示清除已保存的密钥（界面上的“清除密钥”）；非空字符串表示替换（04 第 4 节）。"""

    name: ModelName | None = None
    base_url: BaseUrl | None = None
    api_key: str | None = None
    model: ModelIdentifier | None = None
    temperature: Temperature | None = None
    max_output_tokens: MaxOutputTokens | None = None
    max_tokens_param: MaxTokensParam | None = None
    context_window: ContextWindow | None = None
    timeout_s: TimeoutSeconds | None = None
    concurrency_cap: Concurrency | None = None
    json_mode: bool | None = None
    verify_ssl: bool | None = None
    proxy_url: ProxyUrl = None
    extra_headers: Headers | None = None
    extra_body: dict[str, Any] | None = None
    enabled: bool | None = None
    notes: Notes | None = None


class ModelDraftRequest(Schema):
    """test-draft、list-remote 的请求体。config.api_key 不传或为空字符串：给了 model_id 时用它已保存的密钥，
    否则无密钥；null：无密钥；非空字符串：用这个值（04 第 4 节）。"""

    config: ModelConfigInput
    model_id: int | None = None


class ModelTestResult(Schema):
    ok: bool
    latency_ms: int | None
    status_code: int | None
    error_code: str | None
    message: str
    sample_output: str | None


class RemoteModelList(Schema):
    models: list[str]
