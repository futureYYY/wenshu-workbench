"""上传、粘贴、预览、删除（04 第 7 节）。解析都在工作线程里做，不阻塞事件循环。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy.exc import IntegrityError

from app.api.errors import AppError, bad_request, conflict, field_error, not_found, unprocessable
from app.config import MAX_UPLOAD_BYTES
from app.context import AppContext
from app.db.models import FileRow
from app.db.repo import files as files_repo
from app.db.repo import jobs as jobs_repo
from app.schemas.files import ColumnInfo, FileInfo, FilePage, FilePreview, PreviewRow, SheetInfo
from app.services.file_parser import (
    PHASE2_EXTS,
    SUPPORTED_EXTS,
    FileParseError,
    SourceReader,
    column_stats,
    join_text,
    open_reader,
    suggest_text_columns,
)
from app.services.prompt_render import RowContext
from app.utils import dumps, loads, local_now

logger = logging.getLogger(__name__)

CHUNK = 1024 * 1024
UNSUPPORTED_MESSAGE = "不支持这种文件，支持 txt、md、csv、xlsx、xls"
PHASE2_MESSAGE = "docx、pdf 第二期支持，现在支持 txt、md、csv、xlsx、xls"
TOO_LARGE_MESSAGE = "文件超过 50 MB，请拆分后再上传"


def to_info(row: FileRow, *, reused: bool = False) -> FileInfo:
    meta: dict[str, Any] = loads(row.meta_json, {}) or {}
    kind = "lines" if meta.get("kind") == "lines" else "table"
    sheets = [
        SheetInfo(name=str(s.get("name", "")), row_count=int(s.get("row_count", 0)), truncated=bool(s.get("truncated")))
        for s in meta.get("sheets") or []
    ]
    truncated = bool(meta.get("truncated")) or any(s.truncated for s in sheets)
    return FileInfo(
        id=row.id,
        original_name=row.original_name,
        ext=row.ext,  # type: ignore[arg-type]
        size_bytes=row.size_bytes,
        source="paste" if row.source == "paste" else "upload",
        encoding=row.encoding,
        delimiter=row.delimiter,
        kind=kind,
        sheets=sheets,
        line_count=meta.get("line_count") if kind == "lines" else None,
        truncated=truncated,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        reused=reused,
    )


def stored_path(ctx: AppContext, row: FileRow) -> Path:
    return ctx.cfg.data_dir / row.stored_path


def _ext_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def _check_ext(ext: str) -> None:
    if ext in PHASE2_EXTS:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", PHASE2_MESSAGE)
    if ext not in SUPPORTED_EXTS:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", UNSUPPORTED_MESSAGE)


def _copy_and_hash(src: BinaryIO, dest: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        while True:
            block = src.read(CHUNK)
            if not block:
                break
            size += len(block)
            if size > MAX_UPLOAD_BYTES:
                raise AppError(413, "FILE_TOO_LARGE", TOO_LARGE_MESSAGE)
            digest.update(block)
            out.write(block)
    return digest.hexdigest(), size


def _inspect(path: Path, ext: str) -> tuple[SourceReader, dict[str, Any]]:
    reader = open_reader(path, ext)
    meta = reader.meta()
    return reader, meta


async def _store(ctx: AppContext, tmp: Path, sha: str, size: int, ext: str, name: str, source: str) -> tuple[FileInfo, bool]:
    """已有相同内容时复用（返回 created=False）；否则移到 uploads/<前 2 位>/<sha256>.<扩展名> 并解析元数据。"""
    async with ctx.db.session() as session, session.begin():
        existing = await files_repo.get_by_sha(session, sha)
        if existing is not None:
            await files_repo.touch(session, existing.id)
    if existing is not None:
        tmp.unlink(missing_ok=True)
        async with ctx.db.session() as session:
            row = await files_repo.get(session, existing.id)
        assert row is not None
        return to_info(row, reused=True), False

    relative = Path("uploads") / sha[:2] / f"{sha}.{ext}"
    dest = ctx.cfg.data_dir / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, dest)
    try:
        reader, meta = await asyncio.to_thread(_inspect, dest, ext)
    except FileParseError as exc:
        dest.unlink(missing_ok=True)
        raise unprocessable("FILE_PARSE_FAILED", exc.message) from exc
    except AppError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        logger.exception("解析文件失败：%s", name)
        raise unprocessable("FILE_PARSE_FAILED", "文件已损坏或无法识别") from exc
    ctx.previews.put(dest, reader)
    try:
        async with ctx.db.session() as session, session.begin():
            row = await files_repo.insert(
                session,
                original_name=name,
                stored_path=relative.as_posix(),
                ext=ext,
                size_bytes=size,
                sha256=sha,
                source=source,
                encoding=getattr(reader, "encoding", None),
                delimiter=getattr(reader, "delimiter", None),
                meta_json=dumps(meta),
            )
    except IntegrityError:
        # 同一内容被并发上传：复用先写入的那条
        async with ctx.db.session() as session:
            row = await files_repo.get_by_sha(session, sha)
        if row is None:
            raise
        return to_info(row, reused=True), False
    return to_info(row), True


async def upload(ctx: AppContext, filename: str, fileobj: BinaryIO) -> tuple[FileInfo, bool]:
    name = Path(filename or "未命名").name[:200] or "未命名"
    ext = _ext_of(name)
    _check_ext(ext)
    tmp = ctx.cfg.uploads_dir / "tmp" / uuid.uuid4().hex
    try:
        sha, size = await asyncio.to_thread(_copy_and_hash, fileobj, tmp)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise unprocessable("FILE_PARSE_FAILED", "文件是空的")
    return await _store(ctx, tmp, sha, size, ext, name, "upload")


async def paste(ctx: AppContext, text: str, name: str | None) -> tuple[FileInfo, bool]:
    if not any(line.strip() for line in text.splitlines()):
        raise field_error("text", "不能为空")
    data = text.encode("utf-8")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", TOO_LARGE_MESSAGE)
    sha = hashlib.sha256(data).hexdigest()
    tmp = ctx.cfg.uploads_dir / "tmp" / uuid.uuid4().hex
    tmp.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(tmp.write_bytes, data)
    display = name or f"粘贴文本 {local_now().strftime('%Y-%m-%d %H:%M')}"
    return await _store(ctx, tmp, sha, len(data), "txt", display, "paste")


async def list_files(ctx: AppContext, offset: int, limit: int) -> FilePage:
    async with ctx.db.session() as session:
        rows, total = await files_repo.list_recent(session, offset, limit)
    return FilePage(items=[to_info(r) for r in rows], total=total)


async def get_row(ctx: AppContext, file_id: int) -> FileRow:
    async with ctx.db.session() as session:
        row = await files_repo.get(session, file_id)
    if row is None:
        raise not_found("文件不存在")
    return row


async def get_file(ctx: AppContext, file_id: int) -> FileInfo:
    return to_info(await get_row(ctx, file_id))


async def delete_file(ctx: AppContext, file_id: int) -> None:
    async with ctx.db.session() as session, session.begin():
        row = await files_repo.get(session, file_id)
        if row is None:
            raise not_found("文件不存在")
        active = await jobs_repo.active_count_for_file(session, file_id)
        if active:
            raise conflict("FILE_IN_USE", f"还有 {active} 个排队、运行中或已暂停的任务在使用这个文件，先取消或删除它们")
        await files_repo.delete_file(session, file_id)
    path = stored_path(ctx, row)
    ctx.previews.forget(path)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("删除上传文件失败：%s", path, exc_info=True)


def _reader_for(ctx: AppContext, row: FileRow) -> Any:
    path = stored_path(ctx, row)
    return ctx.previews.get(path, lambda: open_reader(path, row.ext, encoding=row.encoding, delimiter=row.delimiter))


def _preview_sync(ctx: AppContext, row: FileRow, sheet: str | None, header_row: int, offset: int, limit: int) -> FilePreview:
    cached = _reader_for(ctx, row)
    with cached.lock:
        reader: SourceReader = cached.reader
        try:
            sheet_name = reader.resolve_sheet(sheet)
        except KeyError as exc:
            raise bad_request(f"工作表“{sheet}”不存在") from exc
        if reader.kind == "lines":
            header_row = 0
        columns = reader.columns(sheet_name, header_row)
        rows = reader.preview_rows(sheet_name, header_row, offset, limit)
        total, blanks, truncated = reader.data_stats(sheet_name, header_row)
    stats = column_stats(columns, rows)
    return FilePreview(
        sheet=sheet_name,
        header_row=header_row,
        columns=[ColumnInfo(**s) for s in stats],
        suggested_text_columns=suggest_text_columns(stats),
        rows=[PreviewRow(row_number=r.row_number, values=r.values) for r in rows],
        total_rows=total,
        blank_rows=blanks,
        truncated=truncated,
    )


async def preview(ctx: AppContext, file_id: int, sheet: str | None, header_row: int, offset: int, limit: int) -> FilePreview:
    row = await get_row(ctx, file_id)
    try:
        return await asyncio.to_thread(_preview_sync, ctx, row, sheet, header_row, offset, limit)
    except FileParseError as exc:
        raise unprocessable("FILE_PARSE_FAILED", exc.message) from exc


def _sample_row_sync(
    ctx: AppContext, row: FileRow, sheet: str | None, header_row: int, text_columns: list[str], join_mode: str,
    row_number: int,
) -> RowContext:
    cached = _reader_for(ctx, row)
    with cached.lock:
        reader: SourceReader = cached.reader
        try:
            sheet_name = reader.resolve_sheet(sheet)
        except KeyError as exc:
            raise bad_request(f"工作表“{sheet}”不存在") from exc
        if reader.kind == "lines":
            header_row = 0
        columns = reader.columns(sheet_name, header_row)
        found = None
        for data_row in reader.iter_rows(sheet_name, header_row, start_row=row_number):
            if data_row.row_number == row_number:
                found = data_row
            break
    if found is None:
        raise bad_request(f"第 {row_number} 行不在数据范围内")
    keys = {c.key for c in columns}
    missing = [k for k in text_columns if k not in keys]
    if missing:
        raise bad_request(f"文件里没有这些列：{'、'.join(missing)}")
    titles = {c.key: c.title for c in columns}
    text = join_text(found.values, text_columns, titles, join_mode)
    return RowContext(
        text=text,
        row_number=found.row_number,
        file_name=row.original_name,
        row_values=found.values,
        columns=[(c.key, c.title) for c in columns],
    )


async def sample_row(
    ctx: AppContext, file_id: int, sheet: str | None, header_row: int, text_columns: list[str], join_mode: str,
    row_number: int,
) -> RowContext:
    row = await get_row(ctx, file_id)
    try:
        return await asyncio.to_thread(
            _sample_row_sync, ctx, row, sheet, header_row, text_columns, join_mode, row_number
        )
    except FileParseError as exc:
        raise unprocessable("FILE_PARSE_FAILED", exc.message) from exc


def cleanup_tmp(uploads_dir: Path) -> None:
    tmp = uploads_dir / "tmp"
    if tmp.is_dir():
        shutil.rmtree(tmp, ignore_errors=True)
