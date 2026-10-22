"""试运行（04 第 6 节）：使用编辑器里尚未保存的提示词，流式返回原始输出，最后给出解析结果。

不自动重试、不发纠正请求；出错直接发 error 事件。客户端断开时，生成器被取消，上游请求随之关闭。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.api.errors import AppError
from app.context import AppContext
from app.schemas.common import ChatMessage, ClassifyResult, KeyPoint, SummarizeResult, Usage
from app.schemas.prompts import PlaygroundDone, PlaygroundRunRequest
from app.services import model_service, prompt_service, segmenter
from app.services.llm_client import ChatResult, LLMError, ModelSpec
from app.services.output_parser import (
    ClassifyParsed,
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
    chunk_messages,
    effective_max_output,
    effective_temperature,
    merge_budget,
    merge_messages,
    plan_classify,
    plan_summarize,
)

logger = logging.getLogger(__name__)

THINK_HINT = "这个模型会先思考再回答，请调大最大输出，或在额外请求体里关闭思考"


def sse(event: str, data: Any) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def error_event(code: str, message: str, status_code: int | None = None) -> dict[str, str]:
    return sse("error", {"error_code": code, "message": message, "status_code": status_code})


@dataclass
class StageOutput:
    messages: list[dict[str, str]]
    result: ChatResult
    content: str
    reasoning: str | None


@dataclass
class Totals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    last: StageOutput | None = None
    stages: list[StageOutput] = field(default_factory=list)

    def add(self, out: StageOutput) -> None:
        result = out.result
        contents = [m["content"] for m in out.messages]
        self.prompt_tokens += result.prompt_tokens if result.prompt_tokens is not None else segmenter.estimate_messages_tokens(contents)
        self.completion_tokens += (
            result.completion_tokens
            if result.completion_tokens is not None
            else segmenter.estimate_tokens((result.reasoning or "") + result.content)
        )
        self.latency_ms += result.latency_ms
        self.last = out


class _Context:
    def __init__(self, ctx: AppContext, spec: PromptSpec, model: ModelSpec) -> None:
        self.ctx = ctx
        self.spec = spec
        self.model = model
        self.max_output = effective_max_output(spec, model.max_output_tokens)
        self.temperature = effective_temperature(spec, model.temperature)
        self.json_output = spec.output_mode == "json"


async def _stream_stage(run: _Context, messages: list[dict[str, str]], totals: Totals) -> AsyncIterator[dict[str, str]]:
    result: ChatResult | None = None
    async for kind, payload in run.ctx.llm.stream_chat(
        run.model, messages, temperature=run.temperature, max_tokens=run.max_output, json_output=run.json_output
    ):
        if kind == "delta":
            yield sse("delta", {"content": payload})
        elif kind == "reasoning":
            yield sse("reasoning_delta", {"content": payload})
        else:
            result = payload
    assert result is not None
    content, reasoning = strip_reasoning(result.content, result.reasoning)
    totals.add(StageOutput(messages, result, content, reasoning))


def _parse_failure_text(failure: ParseFailure, out: StageOutput, json_output: bool) -> str:
    if json_output and out.result.finish_reason == "length":
        text = "输出被截断，请调大最大输出 tokens"
        if out.reasoning:
            text += f"；{THINK_HINT}"
        return text
    return f"输出无法解析：{failure.reason}"


def _part_text(parsed: SummarizeParsed, json_output: bool) -> str:
    return json.dumps(parsed.result, ensure_ascii=False) if json_output else parsed.summary


def _done(run: _Context, totals: Totals, parsed: Any, parse_error: str | None, chunk_count: int, truncated: bool) -> dict[str, str]:
    last = totals.last
    assert last is not None
    if isinstance(parsed, ClassifyParsed):
        parsed_model: ClassifyResult | SummarizeResult | None = ClassifyResult(
            label=parsed.label, confidence=parsed.confidence, reason=parsed.reason
        )
    elif isinstance(parsed, SummarizeParsed):
        parsed_model = SummarizeResult(
            summary=parsed.summary, key_points=[KeyPoint(text=k["text"], sources=k["sources"]) for k in parsed.key_points]
        )
    else:
        parsed_model = None
    done = PlaygroundDone(
        raw_output=last.result.content,
        reasoning=last.reasoning,
        parsed=parsed_model,
        parse_error=parse_error,
        usage=Usage(prompt_tokens=totals.prompt_tokens, completion_tokens=totals.completion_tokens),
        latency_ms=totals.latency_ms,
        chunk_count=chunk_count,
        truncated=truncated,
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in last.messages],  # type: ignore[arg-type]
    )
    return sse("done", done.model_dump())


async def run(ctx: AppContext, req: PlaygroundRunRequest) -> AsyncIterator[dict[str, str]]:
    try:
        spec = prompt_service.spec_from_draft(req.prompt)
        prompt_service.ensure_valid_for_run(spec)
        model_row, model = await model_service.load_spec(ctx.db, ctx.crypto, req.model_id)
        if not model_row.enabled:
            yield error_event("MODEL_DISABLED", "所选模型已停用")
            return
        row = await prompt_service.resolve_sample(ctx, req.sample)
        if not row.text.strip():
            yield error_event("BAD_REQUEST", "样本是空的，请粘贴一段文本或选一行数据")
            return
        run_ctx = _Context(ctx, spec, model)
        totals = Totals()

        if spec.task_type == "classify":
            plan = plan_classify(spec, row, model.context_window, run_ctx.max_output)
            yield sse("stage", {"name": "request"})
            async for event in _stream_stage(run_ctx, plan.messages.messages, totals):
                yield event
            out = totals.last
            assert out is not None
            if not out.content.strip() and not out.reasoning:
                yield error_event("EMPTY_OUTPUT", "模型返回了空内容", 200)
                return
            try:
                parsed: Any = parse_classify(out.content, spec.field_map, spec.output_mode)
                parse_error = None
            except ParseFailure as failure:
                parsed, parse_error = None, _parse_failure_text(failure, out, run_ctx.json_output)
            yield _done(run_ctx, totals, parsed, parse_error, 1, plan.truncated)
            return

        plan_s = plan_summarize(spec, row, model.context_window, run_ctx.max_output)
        segment_count = len(plan_s.segments)
        if plan_s.single is not None:
            yield sse("stage", {"name": "request"})
            async for event in _stream_stage(run_ctx, plan_s.single.messages, totals):
                yield event
            out = totals.last
            assert out is not None
            if not out.content.strip() and not out.reasoning:
                yield error_event("EMPTY_OUTPUT", "模型返回了空内容", 200)
                return
            try:
                parsed = parse_summarize(out.content, spec.field_map, spec.output_mode, segment_count)
                parse_error = None
            except ParseFailure as failure:
                parsed, parse_error = None, _parse_failure_text(failure, out, run_ctx.json_output)
            yield _done(run_ctx, totals, parsed, parse_error, 1, False)
            return

        # 长文本：依次请求每一段，再合并（合并内容超出预算时分组多轮合并）
        total = len(plan_s.chunks)
        parts: list[str] = []
        for index, chunk in enumerate(plan_s.chunks, start=1):
            yield sse("stage", {"name": "chunk", "index": index, "total": total})
            messages = chunk_messages(spec, row, chunk, index, total).messages
            async for event in _stream_stage(run_ctx, messages, totals):
                yield event
            out = totals.last
            assert out is not None
            try:
                parsed_chunk = parse_summarize(out.content, spec.field_map, spec.output_mode, segment_count)
            except ParseFailure as failure:
                yield error_event("PARSE_ERROR", f"第 {index} 段{_parse_failure_text(failure, out, run_ctx.json_output)}")
                return
            parts.append(_part_text(parsed_chunk, run_ctx.json_output))

        budget = merge_budget(spec, row, model.context_window, run_ctx.max_output)
        final: SummarizeParsed | None = None
        final_error: str | None = None
        while final is None and final_error is None:
            fits = segmenter.estimate_tokens(segmenter.format_chunk_summaries(parts)) <= budget
            groups = [list(range(len(parts)))] if fits or len(parts) <= 2 else segmenter.group_parts(parts, budget)
            last_round = len(groups) == 1
            next_parts: list[str] = []
            for group in groups:
                if len(group) == 1:
                    next_parts.append(parts[group[0]])
                    continue
                yield sse("stage", {"name": "merge"})
                messages = merge_messages(spec, row, [parts[i] for i in group]).messages
                async for event in _stream_stage(run_ctx, messages, totals):
                    yield event
                out = totals.last
                assert out is not None
                try:
                    merged = parse_summarize(out.content, spec.field_map, spec.output_mode, segment_count)
                except ParseFailure as failure:
                    if last_round:
                        final_error = _parse_failure_text(failure, out, run_ctx.json_output)
                        break
                    yield error_event("PARSE_ERROR", f"合并时{_parse_failure_text(failure, out, run_ctx.json_output)}")
                    return
                if last_round:
                    final = merged
                else:
                    next_parts.append(_part_text(merged, run_ctx.json_output))
            parts = next_parts
        yield _done(run_ctx, totals, final, final_error, total, False)
    except LLMError as err:
        message = err.message
        if err.error_code == "RATE_LIMITED" and err.retry_after:
            message = f"被限流（HTTP 429），请 {int(err.retry_after)} 秒后再试"
        yield error_event(err.error_code, message, err.status_code)
    except ContextTooSmall as exc:
        yield error_event("CONTEXT_TOO_SMALL", f"模型上下文长度设置过小（{exc}），放不下提示词和输出")
    except MissingTemplate as exc:
        yield error_event("PROMPT_TEMPLATE_MISSING", str(exc))
    except AppError as err:
        yield error_event(err.code, err.message, err.status)
