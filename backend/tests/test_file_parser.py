"""文件解析与上传预览（02 第 6 节；04 第 7 节；08 第 10.1 节“解析”）。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import MAX_ROWS_PER_SOURCE
from app.security import LocalOnlyMiddleware
from app.services.file_parser import FileParseError, open_reader
from app.services.file_parser.base import build_columns, join_text
from app.services.file_parser.detect import detect_delimiter, detect_encoding, detect_encoding_bytes
from app.services.file_parser.excel_parser import cell_to_str
from app.services.file_parser.text_parser import split_lines

from .conftest import Api

LINES = ["第一行：咨询流量", "", "第三行：办理退订", "第四行：投诉扣费"]


@pytest.mark.parametrize(
    ("encoding", "expected"),
    [("utf-8", "utf-8"), ("utf-8-sig", "utf-8-sig"), ("gb18030", "gb18030"), ("utf-16", "utf-16")],
)
def test_text_encodings(tmp_path: Path, encoding: str, expected: str) -> None:
    path = tmp_path / f"t-{encoding}.txt"
    path.write_text("\n".join(LINES * 20) + "\n", encoding=encoding, newline="")
    assert detect_encoding(path).encoding == expected
    reader = open_reader(path, "txt")
    rows = list(reader.iter_rows(None, 0))
    assert [r.values["text"] for r in rows[:4]] == LINES
    meta = reader.meta()
    assert meta["kind"] == "lines" and meta["line_count"] == 80 and meta["nonempty_line_count"] == 60


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030", "utf-16"])
def test_csv_encodings(tmp_path: Path, encoding: str) -> None:
    path = tmp_path / f"c-{encoding}.csv"
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["编号", "留言"])
        for i in range(50):
            writer.writerow([i, f"请问第 {i} 个快递到哪了"])
    reader = open_reader(path, "csv")
    rows = list(reader.iter_rows("CSV", 1))
    assert rows[0].values == {"编号": "0", "留言": "请问第 0 个快递到哪了"}
    assert rows[0].row_number == 2


@pytest.mark.parametrize("delimiter", [",", "\t", ";", "|"])
def test_delimiters(tmp_path: Path, delimiter: str) -> None:
    path = tmp_path / "d.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow(["a", "b", "c"])
        for i in range(30):
            writer.writerow([i, f"值{i}", "x"])
    reader = open_reader(path, "csv")
    assert reader.delimiter == delimiter  # type: ignore[attr-defined]
    assert [c.key for c in reader.columns("CSV", 1)] == ["a", "b", "c"]


def test_delimiter_fallback_statistics() -> None:
    assert detect_delimiter("a|b|c\n1|2|3\n4|5|6\n") == "|"
    assert detect_delimiter("只有一列\n没有分隔符\n") == ","


def test_quoted_newline_and_semicolon(fixture_files: dict[str, Path]) -> None:
    reader = open_reader(fixture_files["semicolon.csv"], "csv")
    rows = list(reader.iter_rows("CSV", 1))
    assert rows[0].values["问题描述"] == "第一行\n第二行：引号内带换行"
    assert rows[1].values["问题描述"] == "普通的一行；含中文分号"
    assert rows[2].values["问题描述"] == '包含;英文分号的"引号"字段'
    assert [r.row_number for r in rows] == [2, 3, 4, 5]


def test_gb18030_fixture_not_garbled(fixture_files: dict[str, Path]) -> None:
    reader = open_reader(fixture_files["gbk_1000.csv"], "csv")
    assert reader.encoding == "gb18030"  # type: ignore[attr-defined]
    first = next(iter(reader.iter_rows("CSV", 1)))
    assert first.values["城市"] in {"北京", "上海", "广州", "成都", "武汉"}
    assert reader.meta()["sheets"][0]["row_count"] == 1001


def test_utf16_and_bom_txt(fixture_files: dict[str, Path]) -> None:
    for name in ("utf16.txt", "bom.txt"):
        reader = open_reader(fixture_files[name], "txt")
        assert [r.values["text"] for r in reader.iter_rows(None, 0)] == LINES


def test_duplicate_and_empty_headers() -> None:
    columns = build_columns(["名称", "", "名称", "名称", "B"], 6)
    assert [c.key for c in columns] == ["名称", "B(2)", "名称(2)", "名称(3)", "B", "F"]
    assert [c.letter for c in columns] == ["A", "B", "C", "D", "E", "F"]
    assert [c.key for c in build_columns(None, 3)] == ["A", "B", "C"]


def test_header_row_zero_and_three(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    path.write_text("说明行\n第二行说明\n编号,内容\n1,甲\n2,乙\n", encoding="utf-8", newline="")
    reader = open_reader(path, "csv")
    with_header = list(reader.iter_rows("CSV", 3))
    assert [c.key for c in reader.columns("CSV", 3)] == ["编号", "内容"]
    assert [(r.row_number, r.values["内容"]) for r in with_header] == [(4, "甲"), (5, "乙")]
    no_header = list(reader.iter_rows("CSV", 0))
    assert [c.key for c in reader.columns("CSV", 0)] == ["A", "B"]
    assert no_header[0].row_number == 1 and no_header[0].values["A"] == "说明行"


def test_xlsx_multiple_sheets_and_types(fixture_files: dict[str, Path]) -> None:
    reader = open_reader(fixture_files["intent_200.xlsx"], "xlsx")
    assert reader.sheet_names() == ["对话", "说明"]
    meta = reader.meta()
    assert meta["sheets"][0] == {"name": "对话", "row_count": 201, "truncated": False}
    assert meta["sheets"][1]["row_count"] == 5
    rows = list(reader.iter_rows("对话", 1))
    assert len(rows) == 200
    assert rows[0].values["会话ID"] == "10023"            # 整数不带 .0
    assert rows[0].values["时间"] == "2026-09-15 09:00:00"  # 日期时间格式
    total, blanks, truncated = reader.data_stats("对话", 1)
    assert (total, truncated) == (200, False)
    notes = list(reader.iter_rows("说明", 1))
    assert notes[1].values["内容"] == "200"


def test_legacy_xls(fixture_files: dict[str, Path]) -> None:
    reader = open_reader(fixture_files["legacy.xls"], "xls")
    rows = list(reader.iter_rows("旧版", 1))
    assert len(rows) == 10
    assert rows[0].values["编号"] == "1"
    assert rows[0].values["金额"] == "10.5"


def test_cell_conversion() -> None:
    from datetime import date, datetime, time

    assert cell_to_str(10023.0) == "10023"
    assert cell_to_str(3.25) == "3.25"
    assert cell_to_str(datetime(2026, 9, 15)) == "2026-09-15"
    assert cell_to_str(datetime(2026, 9, 15, 8, 30, 5)) == "2026-09-15 08:30:05"
    assert cell_to_str(date(2026, 1, 2)) == "2026-01-02"
    assert cell_to_str(time(9, 5)) == "09:05:00"
    assert cell_to_str(True) == "是" and cell_to_str(False) == "否"
    assert cell_to_str(None) == "" and cell_to_str("  文本  ") == "文本"


def test_truncation_over_100k(fixture_files: dict[str, Path]) -> None:
    reader = open_reader(fixture_files["big_120k.csv"], "csv")
    meta = reader.meta()
    assert meta["sheets"][0]["row_count"] == 120_001
    assert meta["sheets"][0]["truncated"] is True
    total, _blanks, truncated = reader.data_stats("CSV", 1)
    assert total == MAX_ROWS_PER_SOURCE and truncated
    assert sum(1 for _ in reader.iter_rows("CSV", 1)) == MAX_ROWS_PER_SOURCE


def test_broken_xlsx(fixture_files: dict[str, Path]) -> None:
    with pytest.raises(FileParseError) as info:
        open_reader(fixture_files["broken.xlsx"], "xlsx").meta()
    assert "Excel" in info.value.message


def test_encrypted_xlsx_detected(tmp_path: Path) -> None:
    path = tmp_path / "locked.xlsx"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512)
    with pytest.raises(FileParseError) as info:
        open_reader(path, "xlsx")
    assert "打开密码" in info.value.message


def test_join_text() -> None:
    values = {"问题": "快递没到", "补充": "", "渠道": "App"}
    titles = {"问题": "用户问题", "补充": "补充", "渠道": "渠道"}
    assert join_text(values, ["问题"], titles, "labeled") == "快递没到"
    assert join_text(values, ["问题", "补充", "渠道"], titles, "labeled") == "用户问题：快递没到\n渠道：App"
    assert join_text(values, ["问题", "渠道"], titles, "plain") == "快递没到\nApp"
    assert join_text(values, ["补充"], titles, "labeled") == ""


# ---- 接口：上传、复用、预览、删除 ----


def test_upload_preview_and_reuse(api: Api, fixture_files: dict[str, Path]) -> None:
    info = api.upload(fixture_files["intent_200.xlsx"])
    assert info["kind"] == "table" and [s["name"] for s in info["sheets"]] == ["对话", "说明"]
    again = api.client.post("/api/files", files={"file": ("改了名字.xlsx", fixture_files["intent_200.xlsx"].read_bytes())})
    assert again.status_code == 200 and again.json()["reused"] is True and again.json()["id"] == info["id"]

    preview = api.ok(api.get(f"/api/files/{info['id']}/preview", params={"sheet": "对话", "header_row": 1}))
    assert preview["total_rows"] == 200
    assert preview["blank_rows"] == 0
    assert preview["suggested_text_columns"] == ["用户问题"]
    assert len(preview["rows"]) == 200 and preview["rows"][0]["row_number"] == 2
    numeric = {c["key"]: c["numeric_ratio"] for c in preview["columns"]}
    assert numeric["会话ID"] == 1.0 and numeric["时间"] == 1.0

    other = api.ok(api.get(f"/api/files/{info['id']}/preview", params={"sheet": "说明", "header_row": 1}))
    assert other["total_rows"] == 4

    limited = api.ok(api.get(f"/api/files/{info['id']}/preview", params={"sheet": "对话", "offset": 10, "limit": 5}))
    assert [r["row_number"] for r in limited["rows"]] == [12, 13, 14, 15, 16]


def test_upload_errors(api: Api, tmp_path: Path, fixture_files: dict[str, Path]) -> None:
    docx = tmp_path / "a.docx"
    docx.write_bytes(b"PK\x03\x04")
    err = api.error(api.client.post("/api/files", files={"file": ("a.docx", docx.read_bytes())}), 415, "UNSUPPORTED_FILE_TYPE")
    assert "第二期" in err["message"]
    api.error(api.client.post("/api/files", files={"file": ("a.exe", b"MZ")}), 415, "UNSUPPORTED_FILE_TYPE")
    api.error(
        api.client.post("/api/files", files={"file": ("broken.xlsx", fixture_files["broken.xlsx"].read_bytes())}),
        422,
        "FILE_PARSE_FAILED",
    )


async def test_upload_too_large_rejected_before_body() -> None:
    """在读请求体之前按 Content-Length 拒绝（中间件层面验证：根本不会去读请求体）。"""
    reached: list[bool] = []

    async def downstream(scope: dict, receive: object, send: object) -> None:
        reached.append(True)

    async def receive() -> dict:
        raise AssertionError("不应读取请求体")

    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    middleware = LocalOnlyMiddleware(downstream, SimpleNamespace(port=18765))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/files",
        "server": ("127.0.0.1", 18765),
        "headers": [
            (b"host", b"127.0.0.1:18765"),
            (b"x-wenshu-client", b"1"),
            (b"content-length", str(60 * 1024 * 1024).encode()),
        ],
    }
    await middleware(scope, receive, send)
    assert not reached
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"]["code"] == "FILE_TOO_LARGE"


def test_paste_and_lines_preview(api: Api) -> None:
    info = api.paste("甲\n\n乙\n丙")
    assert info["kind"] == "lines" and info["source"] == "paste" and info["line_count"] == 4
    assert info["original_name"].startswith("粘贴文本 ")
    preview = api.ok(api.get(f"/api/files/{info['id']}/preview"))
    assert preview["header_row"] == 0 and preview["sheet"] is None
    assert [c["key"] for c in preview["columns"]] == ["text"]
    assert preview["blank_rows"] == 1 and preview["total_rows"] == 4
    api.error(api.post("/api/files/paste", {"text": "  \n "}), 422, "VALIDATION_ERROR")
    # 和上传一样按内容哈希判断重复：内容相同已存在时 200 且 reused: true，名称沿用已有记录的
    again = api.post("/api/files/paste", {"text": "甲\n\n乙\n丙", "name": "另一个名字"})
    assert again.status_code == 200
    assert again.json()["reused"] is True and again.json()["id"] == info["id"]
    assert again.json()["original_name"] == info["original_name"]


def test_big_file_preview_truncated(api: Api, fixture_files: dict[str, Path]) -> None:
    info = api.upload(fixture_files["big_120k.csv"])
    assert info["truncated"] is True
    preview = api.ok(api.get(f"/api/files/{info['id']}/preview", params={"sheet": "CSV"}))
    assert preview["truncated"] is True and preview["total_rows"] == MAX_ROWS_PER_SOURCE


def test_delete_file(api: Api) -> None:
    info = api.paste("删除测试\n第二行")
    assert api.delete(f"/api/files/{info['id']}").status_code == 204
    api.error(api.get(f"/api/files/{info['id']}"), 404, "NOT_FOUND")


# ---- 审核版新增（08 第 10.1 节“解析”） ----


def test_big_utf8_csv_not_mistaken_for_gbk(fixture_files: dict[str, Path]) -> None:
    """大于 1 MB 的 UTF-8 中文文件，第 1,048,576 字节落在汉字中间：仍识别为 UTF-8（增量解码器，02 第 6.2 节）。"""
    path = fixture_files["utf8_big.csv"]
    assert path.stat().st_size > 1024 * 1024
    guess = detect_encoding(path)
    assert guess.encoding == "utf-8" and guess.lossy is False
    reader = open_reader(path, "csv")
    rows = list(reader.iter_rows("CSV", 1))
    assert rows[0].values["编号"] == "1" and rows[0].values["内容"].startswith("第 1 行：大于 1 MB 的 UTF-8 中文文件")
    assert rows[-1].values["编号"] == str(len(rows))   # 每条记录一行，没有串行
    assert not any("\ufffd" in v for r in rows for v in r.values.values())


def test_incremental_decode_respects_eof() -> None:
    data = "汉字测试".encode()            # 每个汉字 3 字节
    cut = data[:-1]                      # 末尾的汉字不完整
    assert detect_encoding_bytes(cut, at_eof=False).encoding == "utf-8"   # 只是样本截断点
    assert detect_encoding_bytes(cut, at_eof=True).encoding != "utf-8"    # 文件真的在半个汉字处结束
    gbk = "第三步先试 GB18030".encode("gb18030")
    assert detect_encoding_bytes(gbk).encoding == "gb18030"


def test_text_line_numbers_ignore_vertical_tab(tmp_path: Path) -> None:
    """txt 里含 \\x0b、\\x0c 时行号不变：只按 \\r\\n、\\r、\\n 切分（02 第 6.5 节）。"""
    path = tmp_path / "控制字符.txt"
    path.write_text("第一行\x0b仍是第一行\n第二行\x0c还是第二行\r\n第三行\r第四行\n", encoding="utf-8", newline="")
    reader = open_reader(path, "txt")
    rows = list(reader.iter_rows(None, 0))
    assert [r.row_number for r in rows] == [1, 2, 3, 4]
    assert rows[0].values["text"] == "第一行\x0b仍是第一行"
    assert split_lines("甲\n乙\n") == ["甲", "乙"] and split_lines("") == []


def test_csv_row_numbers_count_records(tmp_path: Path) -> None:
    """csv 按记录计行号：引号里带换行的一条记录只算一行（02 第 6.6 节）。"""
    path = tmp_path / "记录.csv"
    # newline=""：否则 Windows 会把 \r\n 写成 \r\r\n，多出三条空记录
    path.write_text('编号,内容\r\n1,"第一行\r\n第二行"\r\n2,普通\r\n', encoding="utf-8", newline="")
    rows = list(open_reader(path, "csv").iter_rows("CSV", 1))
    assert [r.row_number for r in rows] == [2, 3]
