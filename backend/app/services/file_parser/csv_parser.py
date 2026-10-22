"""csv 读取：自动识别编码和分隔符，引号内的换行留在同一单元格（02 第 6.2、6.3 节）。

行号按记录计，不按物理行：引号里带换行的一条记录只算一行（02 第 6.6 节），header_row、start_row 也按记录序号理解。
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.config import MAX_ROWS_PER_SOURCE
from app.services.file_parser.base import FileParseError, SheetScan, SourceReader
from app.services.file_parser.detect import DELIMITER_SAMPLE, detect_delimiter, detect_encoding

CSV_SHEET_NAME = "CSV"

# 单元格可能很长（摘要原文），放宽 csv 模块的字段长度上限
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


class CsvReader(SourceReader):
    kind = "table"

    def __init__(self, path: Path, encoding: str | None = None, delimiter: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.lossy = False
        if encoding is None:
            guess = detect_encoding(path)
            encoding, self.lossy = guess.encoding, guess.lossy
        self.encoding = encoding
        if delimiter is None:
            with self._open() as fh:
                delimiter = detect_delimiter(fh.read(DELIMITER_SAMPLE))
        self.delimiter = delimiter

    def _open(self) -> Any:
        return self.path.open(encoding=self.encoding, errors="replace", newline="")

    def sheet_names(self) -> list[str]:
        return [CSV_SHEET_NAME]

    def resolve_sheet(self, sheet: str | None) -> str | None:
        # csv 只有一个“工作表”，名字固定为 CSV；传别的名字也按它处理
        return CSV_SHEET_NAME

    def iter_raw(self, sheet: str | None) -> Iterator[tuple[int, list[str]]]:
        try:
            with self._open() as fh:
                for index, record in enumerate(csv.reader(fh, delimiter=self.delimiter), start=1):
                    yield index, [cell.strip() for cell in record]
        except (csv.Error, UnicodeError) as exc:
            raise FileParseError(f"无法读取这个 csv 文件：{exc}") from exc

    def scan(self, sheet: str | None) -> SheetScan:
        return super().scan(CSV_SHEET_NAME)

    def meta(self) -> dict[str, Any]:
        scan = self.scan(CSV_SHEET_NAME)
        truncated = scan.raw_count - 1 > MAX_ROWS_PER_SOURCE
        return {
            "kind": "table",
            "sheets": [{"name": CSV_SHEET_NAME, "row_count": scan.raw_count, "truncated": truncated}],
            "line_count": None,
        }
