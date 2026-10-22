"""编码识别与 csv 分隔符识别（02 第 6.2、6.3 节）。"""

from __future__ import annotations

import codecs
import csv
from dataclasses import dataclass
from pathlib import Path

ENCODING_SAMPLE = 1024 * 1024
DELIMITER_SAMPLE = 64 * 1024
CANDIDATE_DELIMITERS = (",", "\t", ";", "|")
_GB_FAMILY = {"gb2312", "gbk", "gb18030", "cp936", "hz", "hz_gb_2312", "gb_2312", "euc_cn", "iso2022_cn"}


@dataclass(frozen=True)
class EncodingGuess:
    encoding: str   # Python 编解码器名，如 utf-8、utf-8-sig、utf-16、gb18030
    lossy: bool     # 无法判断，按 gb18030 解码并替换无法识别的字符


def detect_encoding(path: Path) -> EncodingGuess:
    """取文件前 1 MB 作为样本（不足 1 MB 时就是全文）。"""
    with path.open("rb") as fh:
        raw = fh.read(ENCODING_SAMPLE)
        at_eof = not fh.read(1)
    return detect_encoding_bytes(raw, at_eof=at_eof)


def _strict_decodes(raw: bytes, encoding: str, *, at_eof: bool) -> bool:
    """用增量解码器严格解码样本：没读到文件末尾时（final=False）末尾不完整的多字节字符会被暂存而不报错，
    1 MB 的截断点落在汉字中间时，大于 1 MB 的 UTF-8 文件不会被误判成 GBK。"""
    try:
        codecs.getincrementaldecoder(encoding)("strict").decode(raw, final=at_eof)
    except UnicodeDecodeError:
        return False
    return True


def detect_encoding_bytes(raw: bytes, *, at_eof: bool = True) -> EncodingGuess:
    # 1. BOM
    if raw.startswith(codecs.BOM_UTF8):
        return EncodingGuess("utf-8-sig", False)
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return EncodingGuess("utf-16", False)
    # 2. 样本能按 UTF-8 严格解码
    if _strict_decodes(raw, "utf-8", at_eof=at_eof):
        return EncodingGuess("utf-8", False)
    # 3. 样本能按 GB18030 严格解码（数据以简体中文为主，GBK 文件远比其他编码常见，先试它更可靠）
    if _strict_decodes(raw, "gb18030", at_eof=at_eof):
        return EncodingGuess("gb18030", False)
    # 4. charset-normalizer；GB2312、GBK、GB18030 一类统一用 gb18030
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(raw).best()
    except Exception:  # noqa: BLE001 - 识别库失败时按无法判断处理
        best = None
    if best is not None and best.encoding:
        name = codecs.lookup(best.encoding).name.replace("-", "_")
        if name in _GB_FAMILY or name.startswith("gb"):
            return EncodingGuess("gb18030", False)
        if name.startswith("utf_16"):
            return EncodingGuess("utf-16-le" if name.endswith("le") else "utf-16-be" if name.endswith("be") else "utf-16", False)
        if name.startswith("utf_8"):
            return EncodingGuess("utf-8", False)
        return EncodingGuess(codecs.lookup(best.encoding).name, False)
    # 5. 仍无法判断：按 gb18030 解码并替换无法识别的字符
    return EncodingGuess("gb18030", True)


def detect_delimiter(sample: str) -> str:
    """csv.Sniffer 在前 64 KB 中从 , \\t ; | 里识别；失败时统计前 20 行取最稳定的；都不行用逗号。"""
    snippet = sample[:DELIMITER_SAMPLE]
    try:
        dialect = csv.Sniffer().sniff(snippet, delimiters="".join(CANDIDATE_DELIMITERS))
        if dialect.delimiter in CANDIDATE_DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass
    lines = [ln for ln in snippet.splitlines() if ln.strip()][:20]
    best = ","
    best_score: tuple[int, int] = (0, 0)
    for delimiter in CANDIDATE_DELIMITERS:
        counts = [ln.count(delimiter) for ln in lines]
        positive = [c for c in counts if c > 0]
        if not positive:
            continue
        most_common = max(set(positive), key=positive.count)
        stable = sum(1 for c in counts if c == most_common)
        score = (stable, most_common)
        if score > best_score:
            best, best_score = delimiter, score
    return best
