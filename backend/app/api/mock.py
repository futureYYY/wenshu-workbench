"""演示模型：本机模拟的 OpenAI 兼容接口（04 第 11 节、05 第 8 节）。

任务引擎调用演示模型时和调用真实模型走完全相同的 HTTP 路径（http://127.0.0.1:{端口}/mock/v1）。
/mock 不做 Host 和请求头检查。GET /mock/v1/_stats、POST /mock/v1/_reset 供测试和验收使用，不进 OpenAPI。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.services.segmenter import estimate_tokens

DEMO_CATEGORIES = ["咨询", "办理", "投诉", "建议", "其他"]
_CATEGORY_LINE = re.compile(r"^\s*[-*]\s*([^：:\s]{1,20})\s*[：:]", re.MULTILINE)
_NUMBERED_LINE = re.compile(r"^\[(\d+)\]\s*(.*)$", re.MULTILINE)
_PART_HEADER = re.compile(r"第\s*(\d+)\s*部分[：:]")
# 05 第 8.1 节：最后一条 user 消息里有一行恰好是“第 1 部分：”（第 7.4 节合并格式的开头）时为合并请求。
# 不能用“包含‘第 1 部分’”：分段模板第 1 段的开头“下面是一篇长文的第 1 部分，共 N 部分”也包含这几个字
_MERGE_MARK = re.compile(r"(?m)^第 1 部分：$")
_CLAUSE_SPLIT = re.compile(r"[，,。！？!?；;：:\n]")
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])")
THINK_TEXT = "演示思考过程……"


class MockState:
    """演示模型的运行状态：随机故障率、“首次请求”记录、统计（04 第 11 节，验收用）。"""

    def __init__(self, fail_rate: float) -> None:
        self.fail_rate = fail_rate
        self.seen_first: set[tuple[str, str]] = set()   # (故障类型, sha1(model + 全部消息内容))
        self.inflight = 0
        self.max_inflight = 0
        self.total = 0
        self.by_status: dict[str, int] = {}

    def enter(self) -> None:
        self.inflight += 1
        self.total += 1
        self.max_inflight = max(self.max_inflight, self.inflight)

    def leave(self, status: int) -> None:
        self.inflight = max(0, self.inflight - 1)
        key = str(status)
        self.by_status[key] = self.by_status.get(key, 0) + 1

    def stats(self) -> dict[str, Any]:
        return {"inflight": self.inflight, "max_inflight": self.max_inflight, "total": self.total,
                "by_status": dict(self.by_status)}

    def reset(self) -> None:
        """清零统计（max_inflight 从此刻正在处理的请求数算起），并清空“首次请求”的记录。"""
        self.max_inflight = self.inflight
        self.total = 0
        self.by_status = {}
        self.seen_first.clear()


def _content_key(model: str, messages: list[dict[str, Any]]) -> str:
    """05 第 8.5 节：“首次请求”按请求里的 model + 全部消息内容的 sha1 记录。"""
    digest = hashlib.sha1(model.encode("utf-8"))
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, sort_keys=True)
        digest.update(b"\x00" + content.encode("utf-8"))
    return digest.hexdigest()


def _state(request: Request) -> MockState:
    return request.app.state.ctx.mock


def _error(status: int, message: str, code: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": "mock_error", "code": code}},
        headers=headers or {},
    )


def _hash_int(text: str) -> int:
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16)


def _messages_text(messages: list[dict[str, Any]], role: str) -> list[str]:
    out: list[str] = []
    for message in messages:
        if message.get("role") != role:
            continue
        content = message.get("content")
        if isinstance(content, list):  # 兼容多段内容格式
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        out.append(str(content or ""))
    return out


def _first_sentence(text: str, limit: int) -> str:
    parts = [p for p in _SENTENCE_SPLIT.split(text.strip()) if p.strip()]
    return (parts[0] if parts else text).strip()[:limit]


def _first_clause(text: str, limit: int) -> str:
    parts = [p for p in _CLAUSE_SPLIT.split(text.strip()) if p.strip()]
    return (parts[0] if parts else text).strip()[:limit]


def classify_output(system: str, user: str) -> dict[str, Any]:
    categories = _CATEGORY_LINE.findall(system) or list(DEMO_CATEGORIES)
    seen: list[str] = []
    for name in categories:
        if name not in seen:
            seen.append(name)
    hashed = _hash_int(user)
    positions = [(user.find(name), index, name) for index, name in enumerate(seen) if name in user]
    if positions:
        positions.sort()
        label = positions[0][2]
    else:
        label = seen[hashed % len(seen)]
    confidence = round(0.55 + (hashed % 44) / 100, 2)
    return {"intent": label, "confidence": confidence, "reason": "演示模型：根据文本关键词判断"}


def summarize_output(user: str) -> dict[str, Any]:
    segments = [(int(n), t.strip()) for n, t in _NUMBERED_LINE.findall(user) if t.strip()]
    if not segments:
        lines = [ln.strip() for ln in user.splitlines() if ln.strip()]
        segments = list(enumerate(lines, start=1))
    if not segments:
        return {"summary": "演示摘要：原文为空", "key_points": []}
    summary = "演示摘要：" + _first_sentence(segments[0][1], 80)
    picks: list[tuple[int, str]] = []
    for position in (0, len(segments) // 2, len(segments) - 1):
        candidate = segments[position]
        if candidate not in picks:
            picks.append(candidate)
    key_points = [{"text": _first_clause(t, 40), "sources": [n]} for n, t in picks[:3] if _first_clause(t, 40)]
    return {"summary": summary, "key_points": key_points}


def merge_output(user: str) -> dict[str, Any]:
    headers = list(_PART_HEADER.finditer(user))
    points: list[dict[str, Any]] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(user)
        block = user[header.end() : end].strip()
        start = block.find("{")
        if start < 0:
            continue
        try:
            obj = json.loads(block[start : block.rfind("}") + 1])
        except ValueError:
            continue
        for point in obj.get("key_points") or []:
            if isinstance(point, dict) and point.get("text"):
                points.append({"text": str(point["text"]), "sources": list(point.get("sources") or [])})
    return {"summary": f"演示摘要：合并了 {len(headers) or 1} 部分", "key_points": points[:4]}


def _behaviors(request: Request) -> set[str]:
    raw = request.headers.get("x-mock-behavior", "")
    return {b.strip().lower() for b in raw.split(",") if b.strip()}


def _usage(messages: list[dict[str, Any]], output: str) -> dict[str, int]:
    prompt = sum(estimate_tokens(str(m.get("content") or "")) for m in messages) + 16 * len(messages)
    completion = estimate_tokens(output)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


router = APIRouter(prefix="/mock/v1", tags=["演示模型"])


@router.get("/models")
async def mock_list_models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": "wenshu-demo", "object": "model", "owned_by": "wenshu"}]}


@router.get("/_stats", include_in_schema=False)
async def mock_stats(request: Request) -> dict[str, Any]:
    return _state(request).stats()


@router.post("/_reset", status_code=204, include_in_schema=False)
async def mock_reset(request: Request) -> Response:
    _state(request).reset()
    return Response(status_code=204)


@router.post("/chat/completions")
async def mock_chat_completions(request: Request) -> Response:
    state = _state(request)
    try:
        body = await request.json()
    except ValueError:
        return _error(400, "Request body is not valid JSON (mock)", "invalid_json")
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        return _error(400, "messages is required (mock)", "invalid_request")

    messages: list[dict[str, Any]] = [m for m in body["messages"] if isinstance(m, dict)]
    model = str(body.get("model") or "wenshu-demo")
    stream = bool(body.get("stream"))
    behaviors = _behaviors(request)
    system = "\n".join(_messages_text(messages, "system"))
    users = _messages_text(messages, "user")
    last_user = users[-1] if users else ""

    if "intent" in system:
        kind = "classify"
    elif "summary" in system:
        kind = "merge" if _MERGE_MARK.search(last_user) else "summarize"
    else:
        kind = "echo"

    state.enter()
    status = 500        # 记入 by_status 的状态码；流式响应开始后由生成器负责 leave()
    streaming = False
    try:
        # ---- 延迟 ----
        if "fast" in behaviors:
            delay = random.uniform(0.0, 0.005)
        elif kind in ("summarize", "merge"):
            delay = random.uniform(0.8, 2.5)
        else:
            delay = random.uniform(0.3, 1.2)
        if "slow" in behaviors:
            delay *= 5
        if "timeout" in behaviors:
            await asyncio.sleep(600)

        # ---- 故障模拟 ----
        failure = await _simulated_failure(state, behaviors, kind, stream, model, messages, delay)
        if failure is not None:
            status = failure.status_code
            return failure

        # ---- 生成内容 ----
        if kind == "classify":
            content = json.dumps(classify_output(system, last_user), ensure_ascii=False)
        elif kind == "summarize":
            content = json.dumps(summarize_output(last_user), ensure_ascii=False)
        elif kind == "merge":
            content = json.dumps(merge_output(last_user), ensure_ascii=False)
        else:
            content = "OK"
        if "bad_json" in behaviors:
            content = "好的，我认为这是咨询"
        if "empty" in behaviors:
            content = ""
        finish_reason = "stop"
        if "truncate" in behaviors and content:
            content = content[: max(1, len(content) // 2)]
            finish_reason = "length"
        if "think" in behaviors:
            content = f"<think>{THINK_TEXT}</think>{content}"
        reasoning = THINK_TEXT if "reasoning_field" in behaviors else None

        if not stream:
            await asyncio.sleep(delay)
            message: dict[str, Any] = {"role": "assistant", "content": content}
            if reasoning:
                message["reasoning_content"] = reasoning
            status = 200
            return JSONResponse(
                {
                    "id": f"chatcmpl-mock-{uuid.uuid4().hex[:12]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                    "usage": _usage(messages, (reasoning or "") + content),
                }
            )
        streaming = True
    finally:
        if not streaming:
            state.leave(status)

    # 流式：按 SSE 分块返回，每块 1–4 个字，间隔 15–40 毫秒（fast 时几乎不等待）
    fast = "fast" in behaviors

    async def generate() -> AsyncIterator[bytes]:
        chunk_id = f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        def frame(delta: dict[str, Any], finish: str | None) -> bytes:
            payload = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

        try:
            await asyncio.sleep(delay)
            yield frame({"role": "assistant", "content": ""}, None)
            if reasoning:
                for piece in _pieces(reasoning):
                    yield frame({"reasoning_content": piece}, None)
                    await asyncio.sleep(0.001 if fast else random.uniform(0.015, 0.04))
            for piece in _pieces(content):
                yield frame({"content": piece}, None)
                await asyncio.sleep(0.001 if fast else random.uniform(0.015, 0.04))
            yield frame({}, finish_reason)
            yield b"data: [DONE]\n\n"
        finally:
            state.leave(200)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


async def _simulated_failure(
    state: MockState,
    behaviors: set[str],
    kind: str,
    stream: bool,
    model: str,
    messages: list[dict[str, Any]],
    delay: float,
) -> JSONResponse | None:
    """X-Mock-Behavior 指定的故障和随机故障（05 第 8.5 节）。返回 None 表示正常生成内容。"""
    short = min(delay, 0.2)
    if "auth" in behaviors:
        await asyncio.sleep(short)
        return _error(401, "Invalid API key (mock)", "invalid_api_key")
    if "not_found" in behaviors:
        await asyncio.sleep(short)
        return _error(404, f"The model `{model}` does not exist (mock)", "model_not_found")
    if "context" in behaviors:
        await asyncio.sleep(short)
        return _error(400, "This model's maximum context length is 8192 tokens", "context_length_exceeded")
    if "rate_limit" in behaviors:
        await asyncio.sleep(short)
        return _error(429, "Rate limit exceeded (mock)", "rate_limit", {"Retry-After": "1"})
    if "server_error" in behaviors:
        await asyncio.sleep(short)
        return _error(500, "Internal server error (mock)", "server_error")
    key = _content_key(model, messages)
    if "rate_limit_first" in behaviors and ("429", key) not in state.seen_first:
        state.seen_first.add(("429", key))
        await asyncio.sleep(short)
        return _error(429, "Rate limit exceeded (mock, first request)", "rate_limit", {"Retry-After": "1"})
    if "server_error_first" in behaviors and ("500", key) not in state.seen_first:
        state.seen_first.add(("500", key))
        await asyncio.sleep(short)
        return _error(500, "Internal server error (mock, first request)", "server_error")
    # 随机故障只注入非流式的意图识别和摘要请求（任务引擎发的）；试运行（流式）和测试连接（回显）不重试，从不注入
    injectable = kind != "echo" and not stream
    if injectable and "none" not in behaviors and state.fail_rate > 0 and random.random() < state.fail_rate:
        await asyncio.sleep(short)
        if random.random() < 0.5:
            return _error(429, "Rate limit exceeded (mock, random)", "rate_limit", {"Retry-After": "1"})
        return _error(500, "Internal server error (mock, random)", "server_error")
    return None


def _pieces(text: str) -> list[str]:
    pieces: list[str] = []
    index = 0
    while index < len(text):
        size = random.randint(1, 4)
        pieces.append(text[index : index + size])
        index += size
    return pieces
