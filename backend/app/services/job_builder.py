"""从文件生成条目、预估（04 第 8 节；03 第 4.2 节；05 第 7.1 节）。

建任务时流式读取，每 1,000 行一批写入条目（经写入协程，与引擎写入排序）。
limit 的计数方式：从 start_row 起按行读取，空文本行记为 skipped 条目但不占 limit 名额，直到取满或读完。
“相同文本只调用一次”：同一任务内发给模型的内容完全相同的条目只请求一次，后出现的记为跟随条目（dedup_of 指向
第一次出现的）。判断依据是去重键：按提示词快照渲染出的普通请求的完整消息取 sha1（03 第 4.7 节），不只是原文。
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import field_error, not_found, unprocessable
from app.config import DEMO_BASE_URL, MAX_ROWS_PER_SOURCE
from app.context import AppContext
from app.db.models import FileRow, ModelConfigRow, PromptTemplateRow
from app.db.repo import files as files_repo
from app.db.repo import items as items_repo
from app.db.repo import jobs as jobs_repo
from app.db.repo import models as models_repo
from app.db.repo import prompts as prompts_repo
from app.schemas.common import TASK_TYPE_LABELS
from app.schemas.jobs import JobCreate, JobEstimate
from app.services import file_service, segmenter, settings_service
from app.services.file_parser import Column, FileParseError, SourceReader, join_text, open_reader
from app.services.job_engine.writer import ResultWriter, WriteOp
from app.services.model_service import snapshot_of as model_snapshot_of
from app.services.prompt_render import (
    ContextTooSmall,
    DedupeKeyer,
    PromptSpec,
    RowContext,
    StageVars,
    assemble,
    effective_max_output,
    is_long_text,
    main_budget,
)
from app.utils import dumps

BATCH_ROWS = 1000
NO_ITEMS_MESSAGE = "按所选条件没有可处理的数据"
DEFAULT_LATENCY_MS = {"classify": 1500, "summarize": 4000}
DEMO_LATENCY_MS = {"classify": 750, "summarize": 1650}


@dataclass
class Resolved:
    file_row: FileRow
    prompt_row: PromptTemplateRow
    model_row: ModelConfigRow
    path: Path
    sheet: str | None
    header_row: int
    columns: list[Column]


def _open(path: Path, file_row: FileRow) -> SourceReader:
    return open_reader(path, file_row.ext, encoding=file_row.encoding, delimiter=file_row.delimiter)


def _columns_sync(path: Path, file_row: FileRow, sheet: str | None, header_row: int) -> tuple[str | None, int, list[Column]]:
    reader = _open(path, file_row)
    try:
        sheet_name = reader.resolve_sheet(sheet)
    except KeyError as exc:
        raise field_error("source.sheet", f"工作表“{sheet}”不存在") from exc
    if reader.kind == "lines":
        header_row = 0
    return sheet_name, header_row, reader.columns(sheet_name, header_row)


async def resolve(ctx: AppContext, body: JobCreate) -> Resolved:
    async with ctx.db.session() as session:
        file_row = await files_repo.get(session, body.file_id)
        if file_row is None:
            raise not_found("文件不存在")
        prompt_row = await prompts_repo.get(session, body.prompt_id)
        if prompt_row is None:
            raise not_found("提示词不存在")
        model_row = await models_repo.get(session, body.model_id)
        if model_row is None:
            raise not_found("模型不存在")
    if prompt_row.task_type != body.task_type:
        raise field_error("prompt_id", "提示词的任务类型与任务不一致")
    path = file_service.stored_path(ctx, file_row)
    try:
        sheet, header_row, columns = await asyncio.to_thread(
            _columns_sync, path, file_row, body.source.sheet, body.source.header_row
        )
    except FileParseError as exc:
        raise unprocessable("FILE_PARSE_FAILED", exc.message) from exc
    keys = {c.key for c in columns}
    missing = [k for k in body.source.text_columns if k not in keys]
    if missing:
        raise field_error("source.text_columns", f"文件里没有这些列：{'、'.join(missing)}")
    return Resolved(file_row, prompt_row, model_row, path, sheet, header_row, columns)


def iter_source_items(reader: SourceReader, resolved: Resolved, body: JobCreate) -> Iterator[dict[str, Any]]:
    """按顺序产出 {seq, row_number, text, values}；text 为空的是要跳过的行。"""
    src = body.source
    titles = {c.key: c.title for c in resolved.columns}
    nonempty = 0
    seq = 0
    for row in reader.iter_rows(resolved.sheet, resolved.header_row, start_row=src.start_row):
        if src.limit is not None and nonempty >= src.limit:
            break
        text = join_text(row.values, src.text_columns, titles, src.join_mode)
        seq += 1
        if text:
            nonempty += 1
        yield {"seq": seq, "row_number": row.row_number, "text": text, "values": row.values}


def _take(iterator: Iterator[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    return list(islice(iterator, count))


def _take_keyed(iterator: Iterator[dict[str, Any]], count: int, keyer: DedupeKeyer, file_name: str,
                columns: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """取一批，并在线程里算好每一行的去重键（渲染比较耗时，不放在写入协程里做）。"""
    batch = _take(iterator, count)
    for item in batch:
        row = RowContext(text=item["text"], row_number=item["row_number"], file_name=file_name,
                         row_values=item["values"], columns=columns)
        item["key"] = keyer.key(row)
    return batch


# ---- 预估 ----


@dataclass
class _EstimateStats:
    item_count: int = 0
    skipped: int = 0
    duplicates: int = 0
    long_texts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    extra_requests: int = 0
    unknown: tuple[str, ...] = ()
    context_too_small: bool = False
    capped: bool = False


def _estimate_sync(resolved: Resolved, body: JobCreate, spec: PromptSpec, dedupe: bool) -> _EstimateStats:
    stats = _EstimateStats()
    reader = _open(resolved.path, resolved.file_row)
    model = resolved.model_row
    max_out = effective_max_output(spec, model.max_output_tokens)
    columns = [(c.key, c.title) for c in resolved.columns]
    budget: int | None = None
    overhead_tokens = 0
    seen: dict[str, bool] = {}
    keyer = DedupeKeyer(spec)
    for item in iter_source_items(reader, resolved, body):
        text = item["text"]
        if not text:
            stats.skipped += 1
            continue
        stats.item_count += 1
        row = RowContext(text=text, row_number=item["row_number"], file_name=resolved.file_row.original_name,
                         row_values=item["values"], columns=columns)
        if stats.item_count == 1:
            stage = StageVars(text=text, text_numbered=text)
            rendered = assemble(spec, spec.user_template, row, stage, "user")
            stats.unknown = tuple(rendered.unknown)
            try:
                budget = main_budget(spec, row, model.context_window, max_out)
            except ContextTooSmall:
                stats.context_too_small = True
            overhead_tokens = segmenter.estimate_messages_tokens(
                [m["content"] for m in rendered.messages]
            ) - segmenter.estimate_tokens(text)
        digest = keyer.key(row)
        duplicate = dedupe and digest in seen
        tokens = segmenter.estimate_tokens(text)
        if digest in seen:
            long_text = seen[digest]
        elif budget is None:
            long_text = False
        elif spec.task_type == "classify":
            long_text = tokens > budget
        else:
            long_text = tokens > budget * 0.8 and is_long_text(spec, row, model.context_window, max_out)
        seen.setdefault(digest, long_text)
        if long_text:
            stats.long_texts += 1
        if duplicate:
            stats.duplicates += 1
            continue
        overhead = max(0, overhead_tokens)
        if spec.task_type == "classify":
            stats.prompt_tokens += overhead + (min(tokens, budget) if budget else tokens)
            stats.completion_tokens += 60
        else:
            chunks = max(1, math.ceil(tokens / budget)) if long_text and budget else 1
            requests = chunks + (1 if chunks > 1 else 0)
            stats.extra_requests += requests - 1
            stats.prompt_tokens += overhead * requests + tokens + (tokens // 5 if chunks > 1 else 0)
            stats.completion_tokens += min(max_out, 120 + tokens // 10) * requests
    _total, _blanks, truncated = reader.data_stats(resolved.sheet, resolved.header_row)
    stats.capped = truncated and (body.source.limit is None or stats.item_count < body.source.limit)
    return stats


async def estimate(ctx: AppContext, body: JobCreate) -> JobEstimate:
    resolved = await resolve(ctx, body)
    settings = await settings_service.get_settings(ctx.db)
    dedupe = body.dedupe if body.dedupe is not None else settings.default_dedupe
    spec = PromptSpec.from_mapping(prompts_repo.snapshot_of(resolved.prompt_row))
    try:
        stats = await asyncio.to_thread(_estimate_sync, resolved, body, spec, dedupe)
    except FileParseError as exc:
        raise unprocessable("FILE_PARSE_FAILED", exc.message) from exc
    if stats.item_count == 0:
        raise unprocessable("NO_ITEMS", NO_ITEMS_MESSAGE)

    model = resolved.model_row
    request_count = stats.item_count - stats.duplicates
    is_demo = model.provider_kind == "demo" or model.base_url == DEMO_BASE_URL
    latency = model.avg_latency_ms or (DEMO_LATENCY_MS if is_demo else DEFAULT_LATENCY_MS)[body.task_type]
    concurrency = max(1, min(body.concurrency, model.concurrency_cap))
    seconds = (request_count + stats.extra_requests) * latency / 1000 / concurrency
    low = max(1, math.floor(seconds * 0.7))
    high = max(low, math.ceil(seconds * 1.5))

    warnings: list[str] = []
    if stats.unknown:
        warnings.append(f"提示词里有未知变量 {'、'.join(stats.unknown)}，发送时会原样保留")
    if stats.context_too_small:
        warnings.append(f"模型上下文长度设置过小（{model.context_window}），放不下提示词和输出")
    if stats.long_texts:
        if body.task_type == "classify":
            warnings.append(f"有 {stats.long_texts:,} 行超过模型上下文长度，会截去中间部分后再识别")
        else:
            warnings.append(f"有 {stats.long_texts:,} 行超过模型上下文长度，会分段摘要后再合并")
    if stats.capped:
        warnings.append(f"文件超过 {MAX_ROWS_PER_SOURCE:,} 条，只处理前 {MAX_ROWS_PER_SOURCE:,} 条")
    if not model.enabled:
        warnings.append(f"模型“{model.name}”已停用，请换一个模型")
    if is_demo:
        warnings.append("现在用的是演示模型，结果是模拟的")
    return JobEstimate(
        item_count=stats.item_count,
        skipped_empty=stats.skipped,
        duplicate_count=stats.duplicates,
        request_count=request_count,
        long_text_count=stats.long_texts,
        est_prompt_tokens=stats.prompt_tokens,
        est_completion_tokens=stats.completion_tokens,
        est_seconds=(low, high),
        warnings=warnings,
    )


# ---- 建任务 ----


def _insert_batch_op(job_id: int, batch: list[dict[str, Any]], leaders: dict[str, int], dedupe: bool) -> WriteOp:
    async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> dict[str, int]:
        first_rows: list[dict[str, Any]] = []
        follower_rows: list[dict[str, Any]] = []
        new_leaders: dict[str, int] = {}  # 本批新出现的主条目：去重键 → seq
        for item in batch:
            text = item["text"]
            digest = item["key"]
            row = {
                "job_id": job_id,
                "seq": item["seq"],
                "row_number": item["row_number"],
                "input_text": text,
                "input_chars": len(text),
                "row_values_json": dumps(item["values"]),
                "dedupe_key": digest,
                "dedup_of": None,
                "status": "pending" if text else "skipped",
                "attempts": 0,
                "truncated": False,
                "chunk_count": 1,
                "attempt_log_json": "[]",
                "reviewed": False,
            }
            if not text or not dedupe:
                first_rows.append(row)
            elif digest in leaders:
                row["dedup_of"] = leaders[digest]
                first_rows.append(row)
            elif digest in new_leaders:
                follower_rows.append(row)
            else:
                new_leaders[digest] = item["seq"]
                first_rows.append(row)
        await items_repo.insert_batch(session, first_rows)
        resolved_leaders: dict[str, int] = {}
        if new_leaders:
            seqs = list(new_leaders.values())
            seq_to_id = await items_repo.ids_for_seqs(session, job_id, min(seqs), max(seqs))
            resolved_leaders = {digest: seq_to_id[seq] for digest, seq in new_leaders.items()}
        for row in follower_rows:
            row["dedup_of"] = resolved_leaders[row["dedupe_key"]]
        await items_repo.insert_batch(session, follower_rows)
        return resolved_leaders

    return WriteOp(apply=apply, job_id=job_id, job_event="none")


async def create(ctx: AppContext, body: JobCreate) -> int:
    """建任务并立即开始，返回任务 id。"""
    resolved = await resolve(ctx, body)
    model = resolved.model_row
    if not model.enabled:
        raise unprocessable("MODEL_DISABLED", f"模型“{model.name}”已停用")
    settings = await settings_service.get_settings(ctx.db)
    max_retries = body.max_retries if body.max_retries is not None else settings.default_max_retries
    dedupe = body.dedupe if body.dedupe is not None else settings.default_dedupe
    file_row = resolved.file_row
    name = body.name or f"{Path(file_row.original_name).stem} {TASK_TYPE_LABELS[body.task_type]}"
    src = body.source
    source_json = {
        "sheet": resolved.sheet,
        "header_row": resolved.header_row,
        "columns": [{"key": c.key, "title": c.title, "letter": c.letter, "index": c.index} for c in resolved.columns],
        "text_columns": list(src.text_columns),
        "join_mode": src.join_mode,
        "start_row": src.start_row,
        "limit": src.limit,
        "split_mode": src.split_mode,
    }
    prompt_snapshot = prompts_repo.snapshot_of(resolved.prompt_row)
    keyer = DedupeKeyer(PromptSpec.from_mapping(prompt_snapshot))
    key_columns = [(c.key, c.title) for c in resolved.columns]
    writer = ctx.writer

    async def insert_job(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> int:
        row = await jobs_repo.insert(
            session,
            name=name[:100],
            task_type=body.task_type,
            status="queued",
            status_reason="",
            file_id=file_row.id,
            file_name=file_row.original_name,
            source_json=dumps(source_json),
            prompt_id=resolved.prompt_row.id,
            prompt_version=resolved.prompt_row.version,
            prompt_snapshot_json=dumps(prompt_snapshot),
            model_id=model.id,
            model_snapshot_json=dumps(model_snapshot_of(model)),
            concurrency=body.concurrency,
            max_retries=max_retries,
            dedupe=dedupe,
        )
        return row.id

    job_id = int(await writer.run(insert_job, job_event="none"))
    try:
        try:
            reader = await asyncio.to_thread(_open, resolved.path, file_row)
        except FileParseError as exc:
            raise unprocessable("FILE_PARSE_FAILED", exc.message) from exc
        iterator = iter_source_items(reader, resolved, body)
        leaders: dict[str, int] = {}
        total = 0
        nonempty = 0
        while True:
            try:
                batch = await asyncio.to_thread(
                    _take_keyed, iterator, BATCH_ROWS, keyer, file_row.original_name, key_columns
                )
            except FileParseError as exc:
                raise unprocessable("FILE_PARSE_FAILED", exc.message) from exc
            if not batch:
                break
            total += len(batch)
            nonempty += sum(1 for item in batch if item["text"])
            op = _insert_batch_op(job_id, batch, leaders, dedupe)
            future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
            op.urgent = True
            op.future = future
            writer.submit(op)
            leaders.update(await future)
        if nonempty == 0:
            raise unprocessable("NO_ITEMS", NO_ITEMS_MESSAGE)

        async def finalize(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> None:
            await jobs_repo.update_fields(session, job_id, total_items=total)
            await jobs_repo.recount(session, job_id)
            await files_repo.touch(session, file_row.id)

        await writer.run(finalize, job_id=job_id, job_event="created")
    except BaseException:
        async def drop(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> None:
            await jobs_repo.delete_job(session, job_id)

        try:
            await writer.run(drop, job_event="none")
        except Exception:  # noqa: BLE001 - 回滚失败只记日志，原异常照常抛出
            pass
        raise
    await ctx.manager.start_new(job_id)
    return job_id

