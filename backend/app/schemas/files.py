"""文件与预览（04 第 7 节）。"""

from __future__ import annotations

from typing import Literal

from app.schemas.common import Schema, text_len

FileExt = Literal["txt", "md", "csv", "xlsx", "xls", "docx", "pdf"]
FileKind = Literal["table", "lines"]
PasteName = text_len(1, 100)


class SheetInfo(Schema):
    name: str
    row_count: int
    truncated: bool


class FileInfo(Schema):
    id: int
    original_name: str
    ext: FileExt
    size_bytes: int
    source: Literal["upload", "paste"]
    encoding: str | None
    delimiter: str | None
    kind: FileKind
    sheets: list[SheetInfo]
    line_count: int | None
    truncated: bool
    created_at: str
    last_used_at: str
    reused: bool


class FilePage(Schema):
    items: list[FileInfo]
    total: int


class PasteRequest(Schema):
    text: str
    name: PasteName | None = None


class ColumnInfo(Schema):
    key: str
    title: str
    letter: str | None
    index: int
    avg_chars: float
    empty_ratio: float
    numeric_ratio: float


class PreviewRow(Schema):
    row_number: int
    values: dict[str, str]


class FilePreview(Schema):
    sheet: str | None
    header_row: int
    columns: list[ColumnInfo]
    suggested_text_columns: list[str]
    rows: list[PreviewRow]
    total_rows: int
    blank_rows: int
    truncated: bool
