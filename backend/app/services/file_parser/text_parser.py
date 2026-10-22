"""txt、md：只按 \\r\\n、\\r、\\n 切分，行号从 1 开始（与记事本等编辑器一致），去掉每行首尾空白（02 第 6.5 节）。

不用 str.splitlines()：它还会在 \\x0b、\\x0c、\\x1c–\\x1e、\\x85、\\u2028、\\u2029 处断行，行号就对不上了。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from itertools import islice
from pathlib import Path
from typing import Any

from app.config import MAX_ROWS_PER_SOURCE
from app.services.file_parser.base import Column, FileParseError, Row, SheetScan, SourceReader
from app.services.file_parser.detect import detect_encoding

TEXT_KEY = "text"
TEXT_TITLE = "文本"
LINE_BREAK = re.compile(r"\r\n|\r|\n")


def split_lines(text: str) -> list[str]:
    """按 \\r\\n、\\r、\\n 切分；文件末尾的换行符不算多出一个空行（与 splitlines 对末尾的处理相同）。"""
    if not text:
        return []
    lines = LINE_BREAK.split(text)
    if text.endswith(("\n", "\r")):
        lines.pop()
    return lines


class TextReader(SourceReader):
    kind = "lines"

    def __init__(self, path: Path, encoding: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.lossy = False
        if encoding is None:
            guess = detect_encoding(path)
            encoding, self.lossy = guess.encoding, guess.lossy
        self.encoding = encoding
        self.delimiter = None
        self._lines: list[str] | None = None

    def lines(self) -> list[str]:
        if self._lines is None:
            try:
                text = self.path.read_text(encoding=self.encoding, errors="replace")
            except (OSError, LookupError) as exc:
                raise FileParseError(f"无法识别文件编码：{exc}") from exc
            self._lines = [line.strip() for line in split_lines(text)]
        return self._lines

    def sheet_names(self) -> list[str]:
        return []

    def resolve_sheet(self, sheet: str | None) -> str | None:
        return None

    def iter_raw(self, sheet: str | None) -> Iterator[tuple[int, list[str]]]:
        for index, line in enumerate(self.lines(), start=1):
            yield index, [line]

    def scan(self, sheet: str | None) -> SheetScan:
        lines = self.lines()
        return SheetScan(raw_count=len(lines), blank_rows=[i for i, ln in enumerate(lines, 1) if not ln], max_width=1)

    def columns(self, sheet: str | None, header_row: int) -> list[Column]:
        return [Column(key=TEXT_KEY, title=TEXT_TITLE, letter=None, index=0)]

    def iter_rows(self, sheet: str | None, header_row: int, start_row: int | None = None) -> Iterator[Row]:
        for index, line in enumerate(islice(self.lines(), MAX_ROWS_PER_SOURCE), start=1):
            if start_row is not None and index < start_row:
                continue
            yield Row(row_number=index, values={TEXT_KEY: line})

    def data_stats(self, sheet: str | None, header_row: int) -> tuple[int, int, bool]:
        lines = self.lines()
        total = min(len(lines), MAX_ROWS_PER_SOURCE)
        blanks = sum(1 for ln in lines[:total] if not ln)
        return total, blanks, len(lines) > MAX_ROWS_PER_SOURCE

    def meta(self) -> dict[str, Any]:
        lines = self.lines()
        return {
            "kind": "lines",
            "sheets": [],
            "line_count": len(lines),
            "nonempty_line_count": sum(1 for ln in lines if ln),
            "truncated": len(lines) > MAX_ROWS_PER_SOURCE,
        }
