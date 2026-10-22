"""文件解析：按扩展名选实现（csv → CsvReader；xlsx、xls → ExcelReader；txt、md → TextReader）。"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from app.services.file_parser.base import (
    Column,
    FileParseError,
    Row,
    SourceReader,
    column_stats,
    join_text,
    suggest_text_columns,
)
from app.services.file_parser.csv_parser import CsvReader
from app.services.file_parser.excel_parser import ExcelReader
from app.services.file_parser.text_parser import TEXT_KEY, TEXT_TITLE, TextReader

SUPPORTED_EXTS = ("txt", "md", "csv", "xlsx", "xls")
PHASE2_EXTS = ("docx", "pdf")

__all__ = [
    "PHASE2_EXTS",
    "SUPPORTED_EXTS",
    "TEXT_KEY",
    "TEXT_TITLE",
    "Column",
    "FileParseError",
    "PreviewCache",
    "Row",
    "SourceReader",
    "column_stats",
    "join_text",
    "open_reader",
    "suggest_text_columns",
]


def open_reader(path: Path, ext: str, *, encoding: str | None = None, delimiter: str | None = None) -> SourceReader:
    ext = ext.lower()
    if ext == "csv":
        return CsvReader(path, encoding=encoding, delimiter=delimiter)
    if ext in ("xlsx", "xls"):
        return ExcelReader(path, ext)
    if ext in ("txt", "md"):
        return TextReader(path, encoding=encoding)
    raise FileParseError("不支持这种文件，支持 txt、md、csv、xlsx、xls")


class CachedReader:
    def __init__(self, reader: SourceReader) -> None:
        self.reader = reader
        self.lock = threading.Lock()


class PreviewCache:
    """最近打开的读取器（含扫描结果），预览时复用，避免反复解析大文件。只在工作线程里使用。"""

    def __init__(self, size: int = 3) -> None:
        self.size = size
        self._items: OrderedDict[tuple[str, int], CachedReader] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, path: Path, factory: Callable[[], SourceReader]) -> CachedReader:
        try:
            key = (str(path), path.stat().st_mtime_ns)
        except OSError as exc:
            raise FileParseError("原文件不存在，可能已被删除") from exc
        with self._lock:
            cached = self._items.get(key)
            if cached is not None:
                self._items.move_to_end(key)
                return cached
        reader = CachedReader(factory())
        with self._lock:
            self._items[key] = reader
            self._items.move_to_end(key)
            while len(self._items) > self.size:
                self._items.popitem(last=False)
        return reader

    def put(self, path: Path, reader: SourceReader) -> None:
        try:
            key = (str(path), path.stat().st_mtime_ns)
        except OSError:
            return
        with self._lock:
            self._items[key] = CachedReader(reader)
            while len(self._items) > self.size:
                self._items.popitem(last=False)

    def forget(self, path: Path) -> None:
        with self._lock:
            for key in [k for k in self._items if k[0] == str(path)]:
                self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
