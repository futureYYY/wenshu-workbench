"""token 估算、段落切分与编号、截断、分段与分组（05 第 7 节）。全部是确定性的纯函数。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# 05 第 7.1 节：不依赖分词器（tiktoken 首次使用要联网下载词表）
CJK = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]")

PARAGRAPH_SPLIT_THRESHOLD = 600
SEGMENT_MAX_CHARS = 400
MIN_INPUT_BUDGET = 256
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;])")


def estimate_tokens(s: str) -> int:
    if not s:
        return 0
    cjk = len(CJK.findall(s))
    return math.ceil(cjk * 1.0 + (len(s) - cjk) / 3.5)


def estimate_messages_tokens(contents: list[str]) -> int:
    return sum(estimate_tokens(c) for c in contents) + 16 * len(contents)


def input_budget(context_window: int, max_output_tokens: int, overhead: int, factor: float = 1.0) -> int:
    """input_budget = floor((context_window − 有效最大输出 − overhead) × 0.9)；factor 用于上下文超长兜底（每次 × 0.7）。"""
    return math.floor((context_window - max_output_tokens - overhead) * 0.9 * factor)


# ---- 段落切分与编号（05 第 7.2 节） ----


def split_segments(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    segments: list[str] = []
    for raw in normalized.split("\n"):
        para = raw.strip()
        if not para:
            continue
        if len(para) <= PARAGRAPH_SPLIT_THRESHOLD:
            segments.append(para)
            continue
        segments.extend(_split_long_paragraph(para))
    return segments


def _split_long_paragraph(para: str) -> list[str]:
    out: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(para):
        if not sentence:
            continue
        if len(sentence) > SEGMENT_MAX_CHARS:
            if current.strip():
                out.append(current.strip())
            current = ""
            for start in range(0, len(sentence), SEGMENT_MAX_CHARS):
                piece = sentence[start : start + SEGMENT_MAX_CHARS].strip()
                if piece:
                    out.append(piece)
            continue
        if len(current) + len(sentence) <= SEGMENT_MAX_CHARS:
            current += sentence
        else:
            if current.strip():
                out.append(current.strip())
            current = sentence
    if current.strip():
        out.append(current.strip())
    return out


def number_lines(units: list[tuple[int, str]]) -> str:
    """每段一行：[编号] 段落内容。"""
    return "\n".join(f"[{n}] {t}" for n, t in units)


def numbered_text(segments: list[str]) -> str:
    return number_lines(list(enumerate(segments, start=1)))


# ---- 意图识别的截断（05 第 7.3 节） ----


@dataclass(frozen=True)
class Truncation:
    text: str
    truncated: bool
    omitted: int


def truncate_middle(text: str, budget: int) -> Truncation:
    tokens = estimate_tokens(text)
    if tokens <= budget:
        return Truncation(text, False, 0)
    chars_per_token = len(text) / tokens
    keep = max(0, math.floor(budget * chars_per_token) - 20)
    head = text[: math.floor(keep * 0.7)]
    tail_len = math.floor(keep * 0.3)
    tail = text[len(text) - tail_len :] if tail_len > 0 else ""
    omitted = len(text) - len(head) - len(tail)
    return Truncation(f"{head}\n……（中间省略 {omitted} 字）……\n{tail}", True, omitted)


# ---- 摘要分段（05 第 7.4 节） ----


@dataclass
class Chunk:
    units: list[tuple[int, str]]  # (全文段落编号, 内容)；硬切出来的几块沿用同一个编号

    @property
    def text(self) -> str:
        return "\n".join(t for _, t in self.units)

    @property
    def numbered(self) -> str:
        return number_lines(self.units)


def _hard_split(segment: str, budget_tokens: int) -> list[str]:
    tokens = max(1, estimate_tokens(segment))
    size = max(1, math.floor(max(1, budget_tokens) * len(segment) / tokens))
    return [segment[i : i + size] for i in range(0, len(segment), size)]


def pack_chunks(segments: list[str], budget: int) -> list[Chunk]:
    """把连续的段落依次装进分段，每段不超过预算；单个段落超出预算时按字数硬切。"""
    units: list[tuple[int, str]] = []
    for n, seg in enumerate(segments, start=1):
        prefix_tokens = estimate_tokens(f"[{n}] ") + 1
        if estimate_tokens(seg) + prefix_tokens > budget:
            units.extend((n, piece) for piece in _hard_split(seg, budget - prefix_tokens))
        else:
            units.append((n, seg))
    chunks: list[Chunk] = []
    current: list[tuple[int, str]] = []
    used = 0
    for n, t in units:
        cost = estimate_tokens(f"[{n}] {t}") + 1
        if current and used + cost > budget:
            chunks.append(Chunk(current))
            current, used = [], 0
        current.append((n, t))
        used += cost
    if current:
        chunks.append(Chunk(current))
    return chunks


def format_chunk_summaries(parts: list[str]) -> str:
    """{{chunk_summaries}}：第 1 部分：\\n{…}\\n\\n第 2 部分：\\n{…}"""
    return "\n\n".join(f"第 {i} 部分：\n{p}" for i, p in enumerate(parts, start=1))


def group_parts(parts: list[str], budget: int) -> list[list[int]]:
    """合并内容超出预算时，把相邻的部分分组（每组至少两部分，保证每轮都在减少）。"""
    groups: list[list[int]] = []
    current: list[int] = []
    used = 0
    for index, part in enumerate(parts):
        cost = estimate_tokens(part) + 8
        if len(current) >= 2 and used + cost > budget:
            groups.append(current)
            current, used = [], 0
        current.append(index)
        used += cost
    if current:
        if len(current) == 1 and groups:
            groups[-1].append(current[0])
        else:
            groups.append(current)
    return groups
