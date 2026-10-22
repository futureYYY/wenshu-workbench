"""模型调用：客户端缓存、请求构造、错误分类（05 第 1、6、9 节）。

只调用 Chat Completions。官方 openai SDK 的 AsyncOpenAI，SDK 自带重试关闭，重试由任务引擎负责。
openai 3.x 的底层 HTTP 客户端是 httpx2（SDK 提供 DefaultAsyncHttpx2Client）；为了在 SDK 版本差异下也能工作，
导入时依次尝试 httpx2 和 httpx。
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import openai
from openai import AsyncOpenAI

from app.config import DEMO_BASE_URL

try:  # openai 3.x 的底层客户端是 httpx2
    import httpx2 as _http
except ImportError:  # 兼容仍使用 httpx 的 SDK 版本
    import httpx as _http  # type: ignore[no-redef]

# SDK 提供的默认客户端类（保留了 SDK 的超时、重定向等默认设置）；名字因版本而异，都没有时直接用底层客户端
_DefaultAsyncClient: Any = getattr(openai, "DefaultAsyncHttpx2Client", None) or getattr(
    openai, "DefaultAsyncHttpxClient", None
)

logger = logging.getLogger(__name__)

RETRYABLE_CODES = frozenset({"TIMEOUT", "CONNECTION_ERROR", "RATE_LIMITED", "SERVER_ERROR", "EMPTY_OUTPUT"})
CIRCUIT_CODES = frozenset({"TIMEOUT", "CONNECTION_ERROR", "SERVER_ERROR"})
# 05 第 6.1 节：HTTP 400/413 且错误信息含下列之一（不区分大小写）时为 CONTEXT_TOO_LONG；
# 含 max_tokens、max_completion_tokens 的是最大输出参数超限，按 BAD_REQUEST 处理
_CONTEXT_PHRASES = (
    "context_length",
    "maximum context",
    "context window",
    "context length",
    "prompt is too long",
    "input is too long",
    "超出上下文",
    "上下文长度",
)
_MAX_OUTPUT_PARAMS = ("max_tokens", "max_completion_tokens")
RESERVED_BODY_KEYS = ("model", "messages", "stream")


def is_context_too_long(upstream_message: str) -> bool:
    text = (upstream_message or "").lower()
    if any(param in text for param in _MAX_OUTPUT_PARAMS):
        return False
    return any(phrase in text for phrase in _CONTEXT_PHRASES)


@dataclass
class ModelSpec:
    """发请求用的模型配置（含解密后的密钥，只在内存里）。"""

    id: int | None
    name: str
    provider_kind: str
    base_url: str
    api_key: str | None
    model: str
    temperature: float = 0.3
    max_output_tokens: int = 1024
    max_tokens_param: str = "max_tokens"
    context_window: int = 32768
    timeout_s: int = 120
    concurrency_cap: int = 20
    json_mode: bool = False
    verify_ssl: bool = True
    proxy_url: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""

    @property
    def is_demo(self) -> bool:
        return self.provider_kind == "demo"


class LLMError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        latency_ms: int | None = None,
        upstream_message: str = "",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after
        self.latency_ms = latency_ms
        self.upstream_message = upstream_message

    @property
    def retryable(self) -> bool:
        return self.error_code in RETRYABLE_CODES


@dataclass
class ChatResult:
    content: str
    reasoning: str | None
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    status_code: int = 200
    has_choices: bool = True


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        seconds = parsed.timestamp() - time.time()
    return max(0.0, min(60.0, seconds))


def _upstream_message(exc: openai.APIStatusError) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str):
            return err
        if body.get("message"):
            return str(body["message"])
        if body.get("detail"):
            return str(body["detail"])
    elif isinstance(body, str) and body.strip():
        return body.strip()
    try:
        text = exc.response.text
        if text:
            return text.strip()
    except Exception:  # noqa: BLE001 - 读响应体失败时退回 SDK 的说明
        pass
    return str(getattr(exc, "message", "") or exc)


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not seen for seen in chain) and len(chain) < 8:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def describe_chain(exc: BaseException) -> str:
    """日志用：完整的异常链（类型和说明），不含请求头和密钥。"""
    return " ← ".join(f"{type(e).__name__}: {' '.join(str(e).split()) or '（无说明）'}" for e in _exception_chain(exc))


def _connection_reason(exc: BaseException) -> str:
    """沿异常链从最里层找有内容的说明，并带上异常类型，便于判断是网络、证书还是代理问题。"""
    chain = _exception_chain(exc)
    kind = type(chain[-1]).__name__
    detail = ""
    for err in reversed(chain):
        text = " ".join(str(err).split())
        if text and text.lower().rstrip(".") != "connection error":
            kind, detail = type(err).__name__, text
            break
    lowered = f"{kind} {detail}".lower()
    if "certificate" in lowered or "ssl" in lowered:
        return f"证书校验失败（公司内网自签名证书可在模型配置里关闭“校验证书”）（{kind}）"
    if "refused" in lowered or "10061" in lowered:
        return f"对方拒绝连接，服务可能没有启动（{kind}）"
    if (
        "getaddrinfo" in lowered or "name or service not known" in lowered or "11001" in lowered
        or "nodename" in lowered or "name resolution" in lowered
    ):
        return f"域名解析失败，请检查地址或网络（{kind}）"
    if "socks" in lowered:
        return "使用 socks5 代理需要额外安装 socksio"
    if "proxy" in lowered:
        return f"代理连接失败：{detail[:120]}（{kind}）"
    if "remoteprotocolerror" in lowered or "server disconnected" in lowered:
        return f"对方提前断开了连接（服务端关闭了空闲连接或网关超时）（{kind}）"
    if "connection reset" in lowered or "10054" in lowered or "forcibly closed" in lowered:
        return f"连接被重置（网络不稳定，或被代理、防火墙中断）（{kind}）"
    if not detail:
        return f"网络连接中断（{kind}）"
    return f"{detail[:150]}（{kind}）"


def classify_exception(exc: BaseException, spec: ModelSpec, base_url: str, latency_ms: int | None = None) -> LLMError:
    """把 SDK 抛出的异常归类为 05 第 6.1 节的错误码。"""
    if isinstance(exc, LLMError):
        return exc
    host = urlparse(base_url).netloc or base_url
    if isinstance(exc, openai.APITimeoutError | _http.TimeoutException | TimeoutError):
        return LLMError("TIMEOUT", f"请求超时（{spec.timeout_s} 秒）", latency_ms=latency_ms)
    if isinstance(exc, openai.APIConnectionError):
        logger.warning("连接模型服务失败（%s）：%s", host, describe_chain(exc))
        return LLMError("CONNECTION_ERROR", f"连不上 {host}：{_connection_reason(exc)}", latency_ms=latency_ms)
    if isinstance(exc, openai.APIStatusError):
        status = int(exc.status_code)
        upstream = _upstream_message(exc)
        if status == 429:
            retry_after = _parse_retry_after(exc.response.headers.get("retry-after"))
            return LLMError("RATE_LIMITED", "被限流（HTTP 429）", status_code=status, retry_after=retry_after,
                            latency_ms=latency_ms, upstream_message=upstream)
        if 500 <= status <= 599:
            return LLMError("SERVER_ERROR", f"模型服务出错（HTTP {status}）", status_code=status,
                            latency_ms=latency_ms, upstream_message=upstream)
        if status in (401, 403):
            return LLMError("AUTH_FAILED", f"密钥无效或无权限（HTTP {status}）", status_code=status,
                            latency_ms=latency_ms, upstream_message=upstream)
        if status == 404:
            return LLMError("MODEL_NOT_FOUND", f"模型“{spec.model}”不存在，或接口地址不对（HTTP 404）",
                            status_code=status, latency_ms=latency_ms, upstream_message=upstream)
        if status in (400, 413) and is_context_too_long(upstream):
            return LLMError("CONTEXT_TOO_LONG", "文本超出模型的上下文长度", status_code=status,
                            latency_ms=latency_ms, upstream_message=upstream)
        return LLMError("BAD_REQUEST", f"请求被拒绝（HTTP {status}）：{upstream[:200]}", status_code=status,
                        latency_ms=latency_ms, upstream_message=upstream)
    if isinstance(exc, _http.HTTPError):
        logger.warning("连接模型服务失败（%s）：%s", host, describe_chain(exc))
        return LLMError("CONNECTION_ERROR", f"连不上 {host}：{_connection_reason(exc)}", latency_ms=latency_ms)
    logger.error("模型调用出现未预期的异常", exc_info=exc)
    return LLMError("INTERNAL_ERROR", f"内部错误：{type(exc).__name__}", latency_ms=latency_ms)


def _extra_field(obj: Any, *names: str) -> str | None:
    """非标准字段（reasoning_content、reasoning）从属性或 model_extra 里读取。"""
    if obj is None:
        return None
    extra = getattr(obj, "model_extra", None) or {}
    for name in names:
        value = getattr(obj, name, None)
        if value is None and isinstance(extra, dict):
            value = extra.get(name)
        if isinstance(value, str) and value:
            return value
    return None


class LLMClients:
    """每个模型配置缓存一个 AsyncOpenAI，缓存键 (id, updated_at)；配置修改后重建，旧实例空闲后关闭。"""

    def __init__(self, port_getter: Callable[[], int], *, log_content: bool = False) -> None:
        self._port_getter = port_getter
        self._log_content = log_content
        self._clients: dict[tuple[int, str], AsyncOpenAI] = {}
        self._in_use: dict[int, int] = {}          # id(client) → 进行中的请求数
        self._retired: list[AsyncOpenAI] = []

    def resolve_base_url(self, spec: ModelSpec) -> str:
        if spec.is_demo or spec.base_url == DEMO_BASE_URL:
            return f"http://127.0.0.1:{self._port_getter()}/mock/v1"
        return spec.base_url

    def _build(self, spec: ModelSpec) -> AsyncOpenAI:
        cap = max(1, int(spec.concurrency_cap))
        options: dict[str, Any] = {
            "verify": bool(spec.verify_ssl),
            # 05 第 1.1 节：代理只认模型配置里的 proxy_url，留空直连；trust_env=False 不读 HTTPS_PROXY 等
            # 环境变量和 Windows 系统代理，否则开着代理软件时，发往本机演示模型、内网网关的请求会被送进代理而失败
            "proxy": spec.proxy_url or None,
            "trust_env": False,
            "limits": _http.Limits(max_connections=cap, max_keepalive_connections=cap),
        }
        try:
            if _DefaultAsyncClient is not None:
                http_client = _DefaultAsyncClient(**options)
            else:
                http_client = _http.AsyncClient(
                    **options, timeout=float(spec.timeout_s), follow_redirects=True
                )
        except ImportError as exc:  # 代理地址或底层依赖不可用
            raise LLMError("CONNECTION_ERROR", f"代理不可用：{exc}") from exc
        return AsyncOpenAI(
            base_url=self.resolve_base_url(spec),
            api_key=spec.api_key or "EMPTY",
            timeout=float(spec.timeout_s),
            max_retries=0,
            default_headers=dict(spec.extra_headers or {}),
            http_client=http_client,
        )

    def _acquire(self, spec: ModelSpec) -> tuple[AsyncOpenAI, bool]:
        """返回 (客户端, 是否为临时客户端)。没有 id 的草稿配置用临时客户端，用完即关。"""
        if spec.id is None:
            return self._build(spec), True
        key = (spec.id, spec.updated_at)
        client = self._clients.get(key)
        if client is None:
            for old_key in [k for k in self._clients if k[0] == spec.id]:
                self._retired.append(self._clients.pop(old_key))
            client = self._build(spec)
            self._clients[key] = client
        self._in_use[id(client)] = self._in_use.get(id(client), 0) + 1
        return client, False

    async def _release(self, client: AsyncOpenAI, temporary: bool) -> None:
        if temporary:
            await client.close()
            return
        count = self._in_use.get(id(client), 1) - 1
        if count <= 0:
            self._in_use.pop(id(client), None)
        else:
            self._in_use[id(client)] = count
        for old in list(self._retired):
            if self._in_use.get(id(old), 0) == 0:
                self._retired.remove(old)
                await old.close()

    def build_params(
        self, spec: ModelSpec, messages: list[dict[str, str]], *, temperature: float, max_tokens: int, json_output: bool
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        params: dict[str, Any] = {
            "model": spec.model,
            "messages": messages,
            "temperature": temperature,
            spec.max_tokens_param: int(max_tokens),
        }
        if spec.json_mode and json_output:
            params["response_format"] = {"type": "json_object"}
        extra_body: dict[str, Any] = {}
        for key, value in (spec.extra_body or {}).items():
            if key in RESERVED_BODY_KEYS:
                logger.warning("额外请求体里的 %s 不允许覆盖，已忽略", key)
                continue
            if value is None:
                params.pop(key, None)       # 值为 null 表示“不发送这个参数”
            else:
                extra_body[key] = value
        return params, extra_body

    def _log_request(self, spec: ModelSpec, base_url: str, messages: list[dict[str, str]], latency_ms: int,
                     status: int | str) -> None:
        if not logger.isEnabledFor(logging.DEBUG):
            return
        logger.debug("模型请求 %s/chat/completions model=%s 耗时=%dms 状态=%s", base_url, spec.model, latency_ms, status)
        if self._log_content and messages:
            logger.debug("消息内容（前 200 字）：%s", messages[-1].get("content", "")[:200])

    async def chat(
        self,
        spec: ModelSpec,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        json_output: bool,
        timeout: float | None = None,
    ) -> ChatResult:
        base_url = self.resolve_base_url(spec)
        params, extra_body = self.build_params(
            spec, messages, temperature=temperature, max_tokens=max_tokens, json_output=json_output
        )
        client, temporary = self._acquire(spec)
        started = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                **params, extra_body=extra_body or None, timeout=timeout if timeout is not None else float(spec.timeout_s)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一归类
            latency = int((time.perf_counter() - started) * 1000)
            error = classify_exception(exc, spec, base_url, latency)
            self._log_request(spec, base_url, messages, latency, error.status_code or error.error_code)
            raise error from exc
        finally:
            await self._release(client, temporary)
        latency = int((time.perf_counter() - started) * 1000)
        self._log_request(spec, base_url, messages, latency, 200)
        choices = getattr(resp, "choices", None) or []
        if not choices:
            return ChatResult("", None, None, None, None, latency, has_choices=False)
        choice = choices[0]
        message = getattr(choice, "message", None)
        content = (getattr(message, "content", None) or "") if message is not None else ""
        reasoning = _extra_field(message, "reasoning_content", "reasoning")
        usage = getattr(resp, "usage", None)
        return ChatResult(
            content=str(content),
            reasoning=reasoning,
            finish_reason=getattr(choice, "finish_reason", None),
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            latency_ms=latency,
        )

    async def stream_chat(
        self,
        spec: ModelSpec,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        json_output: bool,
    ) -> AsyncIterator[tuple[str, Any]]:
        """试运行用的流式请求，依次产出 ("reasoning", 文本)、("delta", 文本)，最后 ("done", ChatResult)。

        不发送 stream_options（不少兼容接口不认）。上游不支持流式（400 且错误信息提到 stream）时，
        改用非流式请求，把完整内容作为一个增量发出。调用方取消时关闭上游连接。
        """
        base_url = self.resolve_base_url(spec)
        params, extra_body = self.build_params(
            spec, messages, temperature=temperature, max_tokens=max_tokens, json_output=json_output
        )
        client, temporary = self._acquire(spec)
        started = time.perf_counter()
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        finish_reason: str | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        fallback = False
        try:
            try:
                stream = await client.chat.completions.create(
                    **params, stream=True, extra_body=extra_body or None, timeout=float(spec.timeout_s)
                )
            except openai.APIStatusError as exc:
                if exc.status_code == 400 and "stream" in _upstream_message(exc).lower():
                    fallback = True
                else:
                    raise
            if not fallback:
                try:
                    async for chunk in stream:
                        usage = getattr(chunk, "usage", None)
                        if usage is not None:
                            prompt_tokens = getattr(usage, "prompt_tokens", None) or prompt_tokens
                            completion_tokens = getattr(usage, "completion_tokens", None) or completion_tokens
                        choices = getattr(chunk, "choices", None) or []
                        if not choices:
                            continue
                        choice = choices[0]
                        delta = getattr(choice, "delta", None)
                        piece_reasoning = _extra_field(delta, "reasoning_content", "reasoning")
                        if piece_reasoning:
                            reasoning_parts.append(piece_reasoning)
                            yield "reasoning", piece_reasoning
                        piece = getattr(delta, "content", None) if delta is not None else None
                        if piece:
                            content_parts.append(piece)
                            yield "delta", piece
                        if getattr(choice, "finish_reason", None):
                            finish_reason = choice.finish_reason
                finally:
                    close = getattr(stream, "close", None)
                    if close is not None:
                        await close()
        except asyncio.CancelledError:
            raise
        except GeneratorExit:
            raise
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - started) * 1000)
            raise classify_exception(exc, spec, base_url, latency) from exc
        finally:
            await self._release(client, temporary)

        if fallback:
            result = await self.chat(spec, messages, temperature=temperature, max_tokens=max_tokens,
                                     json_output=json_output)
            if result.reasoning:
                yield "reasoning", result.reasoning
            if result.content:
                yield "delta", result.content
            yield "done", result
            return
        latency = int((time.perf_counter() - started) * 1000)
        self._log_request(spec, base_url, messages, latency, 200)
        yield "done", ChatResult(
            content="".join(content_parts),
            reasoning="".join(reasoning_parts) or None,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency,
        )

    async def list_models(self, spec: ModelSpec) -> list[str]:
        """GET {base_url}/models，解析 data[].id，按字母排序，最多 500 个。"""
        base_url = self.resolve_base_url(spec)
        client, temporary = self._acquire(spec)
        try:
            page = await client.models.list(timeout=float(min(spec.timeout_s, 30)))
        except Exception as exc:  # noqa: BLE001
            raise classify_exception(exc, spec, base_url) from exc
        finally:
            await self._release(client, temporary)
        data = getattr(page, "data", None)
        if not isinstance(data, list):
            raise LLMError("BAD_RESPONSE", "返回的格式不对")
        ids = sorted({str(getattr(m, "id", "") or "") for m in data} - {""})
        if not ids:
            raise LLMError("BAD_RESPONSE", "返回的格式不对")
        return ids[:500]

    async def close_all(self) -> None:
        clients = list(self._clients.values()) + self._retired
        self._clients.clear()
        self._retired.clear()
        for client in clients:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                logger.debug("关闭模型客户端失败", exc_info=True)
