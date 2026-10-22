"""处理一条条目（02 第 5.3 节；05 第 4、6、7 节）：渲染、长文本处理、请求、重试、解析。

两级并发：调用方已经拿到任务级名额；每次发 HTTP 请求前再拿模型级名额，请求结束立即归还。
等待重试期间只归还模型级名额，保留任务级名额。
鉴权失败、模型不存在：返回 status = "pause" 的结果（带原因码），由执行器调用 request_stop 暂停任务，
触发的条目放回 pending（02 第 5.3 节）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from app.config import RAW_OUTPUT_MAX_CHARS, REASONING_MAX_CHARS
from app.db.models import JobItemRow
from app.services import segmenter
from app.services.job_engine import reasons
from app.services.job_engine.limiter import ResizableLimiter
from app.services.job_engine.progress import ProgressTracker
from app.services.llm_client import ChatResult, LLMClients, LLMError, ModelSpec
from app.services.output_parser import (
    ClassifyParsed,
    EmptyOutput,
    ParseFailure,
    SummarizeParsed,
    parse_classify,
    parse_summarize,
    strip_reasoning,
)
from app.services.prompt_render import (
    ContextTooSmall,
    MissingTemplate,
    PromptSpec,
    RowContext,
    chunk_messages,
    effective_max_output,
    effective_temperature,
    local_today,
    main_budget,
    merge_budget,
    merge_messages,
    overhead,
    plan_classify,
    plan_summarize,
)
from app.services.segmenter import input_budget as compute_input_budget
from app.utils import dumps, iso, loads, now_iso, now_utc

logger = logging.getLogger(__name__)

REPAIR_TEMPLATE = "你上一次的输出无法解析：{reason}。请只输出一个符合要求的 JSON 对象，不要输出任何其他文字。"
THINK_HINT = "这个模型会先思考再回答，请调大最大输出，或在额外请求体里关闭思考"
TRUNCATED_MESSAGE = "输出被截断，请调大最大输出 tokens"
MAX_TRUNCATION_TOKENS = 8192
MAX_CONTEXT_RETRIES = 2
CONTEXT_SHRINK = 0.7
ATTEMPT_LOG_KEEP = 10
RETRY_REASONS = {
    "RATE_LIMITED": "限流",
    "TIMEOUT": "请求超时",
    "CONNECTION_ERROR": "连不上模型服务",
    "SERVER_ERROR": "模型服务出错",
    "EMPTY_OUTPUT": "模型返回了空内容",
}


class PauseRequested(Exception):
    """处理器内部使用：需要暂停整个任务（鉴权失败、模型不存在），process() 把它转成 status = "pause" 的结果。"""

    def __init__(self, code: str, reason: str, values: dict[str, Any]) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.values = values


class _ItemFailure(Exception):
    def __init__(self, code: str, message: str, raw: str | None = None, reasoning: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.raw = raw
        self.reasoning = reasoning


class _ContextTooLong(Exception):
    pass


@dataclass
class ItemOutcome:
    status: str                      # succeeded | failed | pause（这一条放回 pending，任务暂停）
    values: dict[str, Any]
    label: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_latency_ms: int | None = None
    pause_code: str | None = None
    pause_reason: str | None = None


@dataclass
class _State:
    item: JobItemRow
    attempts: int
    log: list[dict[str, Any]]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_latency: int = 0
    reasoning_parts: list[str] = field(default_factory=list)
    truncated: bool = False
    omitted_chars: int | None = None
    chunk_count: int = 1
    last_raw: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def add_log(self, phase: str, status_code: int | None, error_code: str | None, message: str,
                latency_ms: int | None) -> None:
        self.log.append(
            {
                "at": now_iso(),
                "attempt": self.attempts,
                "phase": phase,
                "status_code": status_code,
                "error_code": error_code,
                "message": message,
                "latency_ms": latency_ms,
            }
        )
        del self.log[:-ATTEMPT_LOG_KEEP]

    def add_usage(self, result: ChatResult, messages: list[dict[str, str]], reasoning: str | None) -> None:
        contents = [m["content"] for m in messages]
        self.prompt_tokens += (
            result.prompt_tokens if result.prompt_tokens is not None else segmenter.estimate_messages_tokens(contents)
        )
        self.completion_tokens += (
            result.completion_tokens
            if result.completion_tokens is not None
            else segmenter.estimate_tokens((reasoning or "") + result.content)
        )
        self.total_latency += result.latency_ms
        self.last_raw = result.content
        if reasoning:
            self.reasoning_parts.append(reasoning)

    @property
    def reasoning(self) -> str | None:
        text = "\n\n".join(self.reasoning_parts)
        return text[:REASONING_MAX_CHARS] or None

    def common_values(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "attempt_log_json": json.dumps(self.log, ensure_ascii=False),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "truncated": self.truncated,
            "omitted_chars": self.omitted_chars,
            "chunk_count": self.chunk_count,
            "render_meta_json": dumps(self.meta) if self.meta else None,
            "finished_at": now_iso(),
        }


def _retry_wait(retry_no: int, err: LLMError) -> float:
    """第 n 次重试前等待 min(30, 2^(n−1)) + random(0, 0.5) 秒；有 Retry-After 时按它（最长 60 秒）。"""
    if err.retry_after is not None:
        return min(60.0, max(0.0, err.retry_after))
    return min(30.0, 2 ** (retry_no - 1)) + random.uniform(0, 0.5)


class ItemProcessor:
    def __init__(
        self,
        *,
        llm: LLMClients,
        model: ModelSpec,
        prompt: PromptSpec,
        file_name: str,
        columns: list[tuple[str, str]],
        max_retries: int,
        tracker: ProgressTracker,
        model_limiter: ResizableLimiter,
        on_track_change: Callable[[], None],
    ) -> None:
        self.llm = llm
        self.model = model
        self.prompt = prompt
        self.file_name = file_name
        self.columns = columns
        self.max_retries = max_retries
        self.tracker = tracker
        self.model_limiter = model_limiter
        self.on_track_change = on_track_change
        self.max_output = effective_max_output(prompt, model.max_output_tokens)
        self.temperature = effective_temperature(prompt, model.temperature)
        self.json_output = prompt.output_mode == "json"

    # ---- 入口 ----

    def _row(self, item: JobItemRow, today: str | None) -> RowContext:
        return RowContext(
            text=item.input_text,
            row_number=item.row_number,
            file_name=self.file_name,
            row_values={str(k): str(v) for k, v in (loads(item.row_values_json, {}) or {}).items()},
            columns=self.columns,
            today=today,
        )

    def render_meta(self, item: JobItemRow) -> dict[str, Any]:
        """03 第 4.7 节：条目开始处理时记录实际使用的渲染参数，条目详情按它重现发送内容。
        input_budget 按 05 第 7.1 节计算；不足 256 时照样记录，处理时会以 CONTEXT_TOO_SMALL 失败。"""
        today = local_today()
        row = self._row(item, today)
        cost = overhead(self.prompt, self.prompt.user_template, row, "user")
        return {
            "today": today,
            "context_window": self.model.context_window,
            "max_output_tokens": self.max_output,
            "input_budget": compute_input_budget(self.model.context_window, self.max_output, cost),
        }

    async def process(self, item: JobItemRow, meta: dict[str, Any] | None = None) -> ItemOutcome:
        state = _State(item=item, attempts=int(item.attempts or 0), log=list(loads(item.attempt_log_json, []) or []))
        state.meta = dict(meta) if meta is not None else self.render_meta(item)
        row = self._row(item, state.meta.get("today"))
        factor = 1.0
        context_retries = 0
        while True:
            try:
                if factor < 1.0:
                    # 上下文超长兜底后，记录缩小后的输入预算（截断和分段都以它为准）
                    state.meta["input_budget"] = main_budget(
                        self.prompt, row, self.model.context_window, self.max_output, factor
                    )
                if self.prompt.task_type == "classify":
                    return await self._classify(state, row, factor)
                return await self._summarize(state, row, factor)
            except PauseRequested as request:
                return ItemOutcome(
                    status="pause",
                    values=request.values,
                    prompt_tokens=state.prompt_tokens,
                    completion_tokens=state.completion_tokens,
                    pause_code=request.code,
                    pause_reason=request.reason,
                )
            except _ContextTooLong:
                # 05 第 7.5 节：说明上下文长度填大了，预算 × 0.7 后重新截断或分段，最多 2 次
                context_retries += 1
                if context_retries > MAX_CONTEXT_RETRIES:
                    return self._failed(state, "CONTEXT_TOO_LONG", "文本超出模型的上下文长度")
                factor *= CONTEXT_SHRINK
            except ContextTooSmall:
                return self._failed(
                    state,
                    "CONTEXT_TOO_SMALL",
                    f"模型上下文长度设置过小（{self.model.context_window}），放不下提示词和输出",
                )
            except MissingTemplate as exc:
                return self._failed(state, "BAD_REQUEST", str(exc))
            except _ItemFailure as failure:
                return self._failed(state, failure.code, failure.message, raw=failure.raw, reasoning=failure.reasoning)

    def internal_error(self, item: JobItemRow, exc: BaseException) -> ItemOutcome:
        state = _State(item=item, attempts=int(item.attempts or 0), log=list(loads(item.attempt_log_json, []) or []))
        return self._failed(state, "INTERNAL_ERROR", f"内部错误：{type(exc).__name__}")

    # ---- 结果 ----

    def _failed(self, state: _State, code: str, message: str, *, raw: str | None = None,
                reasoning: str | None = None) -> ItemOutcome:
        values = {
            "status": "failed",
            "error_code": code,
            "error_message": message,
            "raw_output": (raw if raw is not None else state.last_raw or None),
            "reasoning": reasoning or state.reasoning,
            "model_used": self.model.model,
            "latency_ms": None,
            **state.common_values(),
        }
        if values["raw_output"]:
            values["raw_output"] = values["raw_output"][:RAW_OUTPUT_MAX_CHARS]
        return ItemOutcome(
            status="failed",
            values=values,
            error_code=code,
            error_message=message,
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
        )

    def _classify_success(self, state: _State, parsed: ClassifyParsed, latency: int) -> ItemOutcome:
        values = {
            "status": "succeeded",
            "label": parsed.label,
            "confidence": parsed.confidence,
            "reason": parsed.reason,
            "result_json": json.dumps(parsed.result, ensure_ascii=False),
            "raw_output": (state.last_raw or "")[:RAW_OUTPUT_MAX_CHARS],
            "reasoning": state.reasoning,
            "error_code": None,
            "error_message": None,
            "model_used": self.model.model,
            "latency_ms": latency,
            **state.common_values(),
        }
        return ItemOutcome(
            status="succeeded",
            values=values,
            label=parsed.label,
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
            model_latency_ms=latency,
        )

    def _summarize_success(self, state: _State, parsed: SummarizeParsed, latency: int,
                           model_latency: int | None) -> ItemOutcome:
        values = {
            "status": "succeeded",
            "summary": parsed.summary,
            "key_points_json": json.dumps(parsed.key_points, ensure_ascii=False),
            "output_chars": parsed.output_chars,
            "result_json": json.dumps(parsed.result, ensure_ascii=False),
            "raw_output": (state.last_raw or "")[:RAW_OUTPUT_MAX_CHARS],
            "reasoning": state.reasoning,
            "error_code": None,
            "error_message": None,
            "model_used": self.model.model,
            "latency_ms": latency,
            **state.common_values(),
        }
        return ItemOutcome(
            status="succeeded",
            values=values,
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
            model_latency_ms=model_latency,
        )

    # ---- 意图识别 ----

    async def _classify(self, state: _State, row: RowContext, factor: float) -> ItemOutcome:
        plan = plan_classify(self.prompt, row, self.model.context_window, self.max_output, factor)
        state.truncated = plan.truncated
        state.omitted_chars = plan.omitted if plan.truncated else None
        fm, mode = self.prompt.field_map, self.prompt.output_mode
        parsed, result = await self._stage(
            state, plan.messages.messages, "request", "request", "", lambda content: parse_classify(content, fm, mode)
        )
        return self._classify_success(state, parsed, result.latency_ms)

    # ---- 文本摘要 ----

    async def _summarize(self, state: _State, row: RowContext, factor: float) -> ItemOutcome:
        plan = plan_summarize(self.prompt, row, self.model.context_window, self.max_output, factor)
        segment_count = len(plan.segments)
        fm, mode = self.prompt.field_map, self.prompt.output_mode

        def parse(content: str) -> SummarizeParsed:
            return parse_summarize(content, fm, mode, segment_count)

        if plan.single is not None:
            state.chunk_count = 1
            parsed, result = await self._stage(state, plan.single.messages, "request", "request", "", parse)
            return self._summarize_success(state, parsed, result.latency_ms, result.latency_ms)

        total = len(plan.chunks)
        state.chunk_count = total
        parts: list[str] = []
        for index, chunk in enumerate(plan.chunks, start=1):
            messages = chunk_messages(self.prompt, row, chunk, index, total).messages
            parsed_chunk, _ = await self._stage(
                state, messages, f"chunk {index}/{total}", "chunk", f"第 {index}/{total} 段", parse
            )
            parts.append(self._part_text(parsed_chunk))

        budget = merge_budget(self.prompt, row, self.model.context_window, self.max_output, factor)
        while True:
            fits = segmenter.estimate_tokens(segmenter.format_chunk_summaries(parts)) <= budget
            groups = [list(range(len(parts)))] if fits or len(parts) <= 2 else segmenter.group_parts(parts, budget)
            next_parts: list[str] = []
            final: SummarizeParsed | None = None
            for group in groups:
                if len(group) == 1:
                    next_parts.append(parts[group[0]])
                    continue
                messages = merge_messages(self.prompt, row, [parts[i] for i in group]).messages
                merged, _ = await self._stage(state, messages, "merge", "merge", "合并各段摘要", parse)
                if len(groups) == 1:
                    final = merged
                else:
                    next_parts.append(self._part_text(merged))
            if final is not None:
                return self._summarize_success(state, final, state.total_latency, None)
            parts = next_parts

    def _part_text(self, parsed: SummarizeParsed) -> str:
        """{{chunk_summaries}} 的每一部分：JSON 模式为该段解析出的对象，纯文本模式为该段的文字。"""
        return json.dumps(parsed.result, ensure_ascii=False) if self.json_output else parsed.summary

    # ---- 一个阶段：请求 + 解析，含截断翻倍和纠正请求 ----

    async def _stage(
        self,
        state: _State,
        messages: list[dict[str, str]],
        phase: str,
        track_phase: str,
        track_detail: str,
        parse: Callable[[str], Any],
    ) -> tuple[Any, ChatResult]:
        max_tokens = self.max_output
        truncation_retried = False
        repaired = False
        current = messages
        current_phase, current_track, current_detail = phase, track_phase, track_detail
        while True:
            result, content, reasoning = await self._request(
                state, current, current_phase, current_track, current_detail, max_tokens
            )
            try:
                parsed = parse(content)
            except EmptyOutput as exc:
                state.add_log(current_phase, 200, "EMPTY_OUTPUT", "模型返回了空内容", result.latency_ms)
                raise _ItemFailure("EMPTY_OUTPUT", "模型返回了空内容", raw=result.content, reasoning=reasoning) from exc
            except ParseFailure as failure:
                if self.json_output and result.finish_reason == "length":
                    if not truncation_retried and max_tokens < MAX_TRUNCATION_TOKENS:
                        truncation_retried = True
                        max_tokens = min(MAX_TRUNCATION_TOKENS, max_tokens * 2)
                        state.add_log(
                            current_phase, 200, "OUTPUT_TRUNCATED",
                            f"输出被截断，把最大输出调到 {max_tokens} 后重试", result.latency_ms,
                        )
                        continue
                    message = TRUNCATED_MESSAGE + (f"。{THINK_HINT}" if reasoning else "")
                    state.add_log(current_phase, 200, "OUTPUT_TRUNCATED", message, result.latency_ms)
                    raise _ItemFailure("OUTPUT_TRUNCATED", message, raw=result.content, reasoning=reasoning) from failure
                if not repaired:
                    # 05 第 4.4 节：发一次纠正请求（计入 attempts，不占网络重试次数）
                    repaired = True
                    state.add_log(
                        current_phase, 200, "PARSE_ERROR", f"输出无法解析：{failure.reason}，发送纠正请求",
                        result.latency_ms,
                    )
                    current = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": REPAIR_TEMPLATE.format(reason=failure.reason)},
                    ]
                    current_phase, current_track, current_detail = "parse_repair", "parse_repair", "纠正输出格式"
                    continue
                message = f"输出无法解析：{failure.reason}"
                state.add_log(current_phase, 200, "PARSE_ERROR", message, result.latency_ms)
                raise _ItemFailure("PARSE_ERROR", message, raw=result.content, reasoning=reasoning) from failure
            note = "成功"
            if not self.json_output and result.finish_reason == "length":
                note = "输出达到最大长度，可能不完整"
            state.add_log(current_phase, 200, None, note, result.latency_ms)
            return parsed, result

    # ---- 一次请求单元：网络重试与等待 ----

    def _track(self, item_id: int, **fields: Any) -> None:
        self.tracker.update(item_id, **fields)
        self.on_track_change()

    async def _request(
        self,
        state: _State,
        messages: list[dict[str, str]],
        phase: str,
        track_phase: str,
        track_detail: str,
        max_tokens: int,
    ) -> tuple[ChatResult, str, str | None]:
        item_id = state.item.id
        retries_left = self.max_retries
        retry_no = 0
        while True:
            state.attempts += 1
            self._track(item_id, attempt=state.attempts, phase=track_phase, phase_detail=track_detail, retry_at=None)
            await self.model_limiter.acquire()
            try:
                result = await self.llm.chat(
                    self.model, messages, temperature=self.temperature, max_tokens=max_tokens,
                    json_output=self.json_output,
                )
            except LLMError as err:
                self.model_limiter.release()
                if err.error_code in ("AUTH_FAILED", "MODEL_NOT_FOUND"):
                    state.add_log(phase, err.status_code, err.error_code, err.message, err.latency_ms)
                    code, reason = self._pause_reason(err)
                    raise PauseRequested(code, reason, self._pending_values(state)) from err
                if err.error_code == "CONTEXT_TOO_LONG":
                    state.add_log(phase, err.status_code, err.error_code, err.message, err.latency_ms)
                    raise _ContextTooLong() from err
                if not err.retryable or retries_left <= 0:
                    state.add_log(phase, err.status_code, err.error_code, err.message, err.latency_ms)
                    raise _ItemFailure(err.error_code, err.message) from err
                retries_left -= 1
                retry_no += 1
                wait = _retry_wait(retry_no, err)
                state.add_log(
                    phase, err.status_code, err.error_code, f"{err.message}，{math.ceil(wait)} 秒后重试", err.latency_ms
                )
                await self._wait(item_id, err.error_code, wait)
                continue
            except BaseException:
                self.model_limiter.release()
                raise
            self.model_limiter.release()
            content, reasoning = strip_reasoning(result.content, result.reasoning)
            state.add_usage(result, messages, reasoning)
            if not content.strip() and not reasoning:
                if retries_left <= 0:
                    state.add_log(phase, 200, "EMPTY_OUTPUT", "模型返回了空内容", result.latency_ms)
                    raise _ItemFailure("EMPTY_OUTPUT", "模型返回了空内容", raw=result.content)
                retries_left -= 1
                retry_no += 1
                empty = LLMError("EMPTY_OUTPUT", "模型返回了空内容")
                wait = _retry_wait(retry_no, empty)
                state.add_log(phase, 200, "EMPTY_OUTPUT", f"模型返回了空内容，{math.ceil(wait)} 秒后重试",
                              result.latency_ms)
                await self._wait(item_id, "EMPTY_OUTPUT", wait)
                continue
            return result, content, reasoning

    async def _wait(self, item_id: int, code: str, seconds: float) -> None:
        reason = RETRY_REASONS.get(code, "请求失败")
        retry_at = iso(now_utc() + timedelta(seconds=seconds))
        self._track(
            item_id, phase="waiting_retry", phase_detail=f"{reason}，{math.ceil(seconds)} 秒后重试", retry_at=retry_at
        )
        await asyncio.sleep(seconds)

    def _pause_reason(self, err: LLMError) -> tuple[str, str]:
        """03 第 6.1 节的原因码和标准文案。"""
        if err.error_code == "AUTH_FAILED":
            return reasons.AUTH_FAILED, reasons.auth_failed_text(err.status_code)
        return reasons.MODEL_NOT_FOUND, reasons.model_not_found_text(self.model.model)

    def _pending_values(self, state: _State) -> dict[str, Any]:
        return {
            "status": "pending",
            "attempts": state.attempts,
            "attempt_log_json": json.dumps(state.log, ensure_ascii=False),
            "started_at": None,
        }
