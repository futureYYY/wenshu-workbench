"""文件读取的统一接口（02 第 6.1 节）与表格类的共用逻辑：表头、列 key、数据行、扫描统计。"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import islice
from typing import Any

from app.config import MAX_ROWS_PER_SOURCE


class FileParseError(Exception):
    """文件损坏、加密或编码无法识别（422 FILE_PARSE_FAILED）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    letter: str | None
    index: int


@dataclass(frozen=True)
class Row:
    row_number: int
    values: dict[str, str]


@dataclass
class SheetScan:
    """一次完整扫描的结果：原始行数（含表头和前导空行）、整行全空的行号、最大列数。"""

    raw_count: int
    blank_rows: list[int] = field(default_factory=list)
    max_width: int = 0


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def build_columns(header: list[str] | None, width: int) -> list[Column]:
    """03 第 4.2 节的列 key 规则：表头非空且唯一时等于表头文本；为空用列字母；重名从第二个起加 (2)、(3)。

    表头文本优先：空表头的列字母与某个表头文本相同时，给列字母加后缀。无表头时一律用列字母。
    """
    width = max(width, len(header or []))
    titles = [(header[i] if header and i < len(header) else "").strip() for i in range(width)]
    keys: list[str | None] = [None] * width
    used: set[str] = set()
    counts: dict[str, int] = {}
    if header:
        for index, title in enumerate(titles):
            if not title:
                continue
            counts[title] = counts.get(title, 0) + 1
            key = title if counts[title] == 1 else f"{title}({counts[title]})"
            keys[index] = key
            used.add(key)
    columns: list[Column] = []
    for index in range(width):
        letter = column_letter(index)
        key = keys[index]
        if key is None:
            key, suffix = letter, 1
            while key in used:
                suffix += 1
                key = f"{letter}({suffix})"
            used.add(key)
        columns.append(Column(key=key, title=titles[index] or letter, letter=letter, index=index))
    return columns


class SourceReader:
    """表格类读取器的基类；子类实现 sheet_names()、iter_raw()、row_count()。"""

    kind = "table"

    def __init__(self) -> None:
        self._scans: dict[str | None, SheetScan] = {}

    # ---- 子类实现 ----
    def sheet_names(self) -> list[str]:
        raise NotImplementedError

    def iter_raw(self, sheet: str | None) -> Iterator[tuple[int, list[str]]]:
        """按原文件行号（从 1 开始）逐行返回单元格字符串。"""
        raise NotImplementedError

    def row_count(self, sheet: str | None) -> int:
        return self.scan(sheet).raw_count

    def meta(self) -> dict[str, Any]:
        raise NotImplementedError

    # ---- 共用逻辑 ----
    def resolve_sheet(self, sheet: str | None) -> str | None:
        names = self.sheet_names()
        if not names:
            return None
        if sheet is None:
            return names[0]
        if sheet not in names:
            raise KeyError(sheet)
        return sheet

    def scan(self, sheet: str | None) -> SheetScan:
        cached = self._scans.get(sheet)
        if cached is not None:
            return cached
        raw_count = 0
        width = 0
        blanks: list[int] = []
        for row_number, cells in self.iter_raw(sheet):
            raw_count = row_number
            width = max(width, len(cells))
            if not any(c for c in cells):
                blanks.append(row_number)
        result = SheetScan(raw_count=raw_count, blank_rows=blanks, max_width=width)
        self._scans[sheet] = result
        return result

    def set_scan(self, sheet: str | None, scan: SheetScan) -> None:
        self._scans[sheet] = scan

    def header_values(self, sheet: str | None, header_row: int) -> list[str] | None:
        if header_row <= 0:
            return None
        for row_number, cells in self.iter_raw(sheet):
            if row_number == header_row:
                return cells
            if row_number > header_row:
                break
        return []

    def columns(self, sheet: str | None, header_row: int) -> list[Column]:
        return build_columns(self.header_values(sheet, header_row), self.scan(sheet).max_width)

    def iter_rows(self, sheet: str | None, header_row: int, start_row: int | None = None) -> Iterator[Row]:
        """数据行：表头之后最多 10 万行；start_row 为原文件行号，之前的行跳过。"""
        columns = self.columns(sheet, header_row)
        keys = [c.key for c in columns]
        first_data = max(header_row, 0) + 1
        last_data = first_data + MAX_ROWS_PER_SOURCE - 1
        for row_number, cells in self.iter_raw(sheet):
            if row_number < first_data:
                continue
            if row_number > last_data:
                break
            if start_row is not None and row_number < start_row:
                continue
            values = {keys[i] if i < len(keys) else column_letter(i): cells[i] for i in range(len(cells))}
            for key in keys:
                values.setdefault(key, "")
            yield Row(row_number=row_number, values=values)

    def data_stats(self, sheet: str | None, header_row: int) -> tuple[int, int, bool]:
        """(数据行数：不含表头、含空行、最多 10 万；整行全空的行数；是否截断)。"""
        scan = self.scan(sheet)
        first_data = max(header_row, 0) + 1
        available = max(0, scan.raw_count - first_data + 1)
        total = min(available, MAX_ROWS_PER_SOURCE)
        last_data = first_data + total - 1
        blanks = sum(1 for r in scan.blank_rows if first_data <= r <= last_data)
        return total, blanks, available > MAX_ROWS_PER_SOURCE

    def preview_rows(self, sheet: str | None, header_row: int, offset: int, limit: int) -> list[Row]:
        return list(islice(self.iter_rows(sheet, header_row), offset, offset + limit))


# ---- 预览的列统计（04 第 7 节 ColumnInfo） ----

_NUMBER = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?%?$")
_DATE = re.compile(
    r"^\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?([ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?)?$|^\d{1,2}:\d{2}(:\d{2})?$"
)


def is_numeric_like(value: str) -> bool:
    v = value.strip()
    return bool(_NUMBER.match(v) or _DATE.match(v))


def column_stats(columns: list[Column], rows: list[Row]) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    total = len(rows)
    for col in columns:
        values = [r.values.get(col.key, "") for r in rows]
        non_empty = [v for v in values if v.strip()]
        avg = round(sum(len(v) for v in non_empty) / len(non_empty), 1) if non_empty else 0.0
        empty_ratio = round((total - len(non_empty)) / total, 3) if total else 1.0
        numeric = sum(1 for v in non_empty if is_numeric_like(v))
        numeric_ratio = round(numeric / len(non_empty), 3) if non_empty else 0.0
        stats.append(
            {
                "key": col.key,
                "title": col.title,
                "letter": col.letter,
                "index": col.index,
                "avg_chars": avg,
                "empty_ratio": empty_ratio,
                "numeric_ratio": numeric_ratio,
            }
        )
    return stats


def suggest_text_columns(stats: list[dict[str, Any]]) -> list[str]:
    """推荐的文本列：numeric_ratio < 0.5 中 avg_chars 最大的一列。"""
    candidates = [s for s in stats if s["numeric_ratio"] < 0.5 and s["avg_chars"] > 0]
    if not candidates:
        return []
    best = max(candidates, key=lambda s: (s["avg_chars"], -s["index"]))
    return [best["key"]]


def join_text(values: dict[str, str], text_columns: list[str], titles: dict[str, str], join_mode: str) -> str:
    """02 第 6.7 节：labeled 每列一行“列标题：值”；plain 只取值；只选一列时都是值本身。"""
    parts: list[str] = []
    single = len(text_columns) == 1
    for key in text_columns:
        value = (values.get(key) or "").strip()
        if not value:
            continue
        if single or join_mode == "plain":
            parts.append(value)
        else:
            parts.append(f"{titles.get(key, key)}：{value}")
    return "\n".join(parts)
