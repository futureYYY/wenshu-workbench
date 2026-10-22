"""xlsx、xls 读取：python-calamine 只读、流式（02 第 6.4 节）。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from app.config import MAX_ROWS_PER_SOURCE
from app.services.file_parser.base import FileParseError, SourceReader

OLE_MAGIC = b"\xd0\xcf\x11\xe0"
ENCRYPTED_MESSAGE = "这个 Excel 文件设置了打开密码，请另存为无密码的文件后再上传"
BROKEN_MESSAGE = "文件已损坏或不是有效的 Excel 文件"


def cell_to_str(value: Any) -> str:
    """空值为空字符串；整数值的浮点数去掉 .0；日期时间 YYYY-MM-DD HH:MM:SS（时间为零只留日期）；布尔为是/否。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return repr(value)
    if isinstance(value, datetime):
        if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        hours, rem = divmod(abs(seconds), 3600)
        minutes, secs = divmod(rem, 60)
        return f"{'-' if seconds < 0 else ''}{hours}:{minutes:02d}:{secs:02d}"
    return str(value).strip()


class ExcelReader(SourceReader):
    kind = "table"

    def __init__(self, path: Path, ext: str) -> None:
        super().__init__()
        self.path = path
        with path.open("rb") as fh:
            head = fh.read(8)
        if ext == "xlsx" and head.startswith(OLE_MAGIC):
            raise FileParseError(ENCRYPTED_MESSAGE)
        try:
            from python_calamine import CalamineWorkbook

            self._workbook = CalamineWorkbook.from_path(str(path))
            self._names: list[str] = list(self._workbook.sheet_names)
        except Exception as exc:  # noqa: BLE001 - calamine 对损坏文件抛出各种异常
            raise FileParseError(BROKEN_MESSAGE) from exc
        self._sheets: dict[str, Any] = {}

    def sheet_names(self) -> list[str]:
        return list(self._names)

    def _sheet(self, name: str | None) -> Any:
        sheet_name = self.resolve_sheet(name)
        if sheet_name is None:
            return None
        if sheet_name not in self._sheets:
            try:
                self._sheets[sheet_name] = self._workbook.get_sheet_by_name(sheet_name)
            except Exception as exc:  # noqa: BLE001
                raise FileParseError(BROKEN_MESSAGE) from exc
        return self._sheets[sheet_name]

    def row_count(self, sheet: str | None) -> int:
        """工作表已用区域的总行数（含表头和前导空行），取工作表尺寸。"""
        data = self._sheet(sheet)
        if data is None:
            return 0
        end = getattr(data, "end", None)
        if end:
            return int(end[0]) + 1
        start = getattr(data, "start", None) or (0, 0)
        return int(start[0]) + int(getattr(data, "height", 0) or 0)

    def iter_raw(self, sheet: str | None) -> Iterator[tuple[int, list[str]]]:
        data = self._sheet(sheet)
        if data is None:
            return
        start = getattr(data, "start", None)
        if not start:
            return
        first_row, first_col = int(start[0]), int(start[1])
        pad = [""] * first_col
        try:
            iterator = data.iter_rows() if hasattr(data, "iter_rows") else iter(data.to_python(skip_empty_area=True))
            for offset, cells in enumerate(iterator):
                yield first_row + offset + 1, pad + [cell_to_str(c) for c in cells]
        except FileParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FileParseError(BROKEN_MESSAGE) from exc

    def meta(self) -> dict[str, Any]:
        sheets = []
        for name in self._names:
            rows = self.row_count(name)
            sheets.append({"name": name, "row_count": rows, "truncated": rows - 1 > MAX_ROWS_PER_SOURCE})
        return {"kind": "table", "sheets": sheets, "line_count": None}
