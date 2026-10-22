"""输出解析（05 第 4、5 节）：思考内容剥离、JSON 提取、字段映射、类别规范化。全部是纯函数。"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

import json_repair

from app.config import REASONING_MAX_CHARS

_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)
_FENCE = re.compile(r"^```[A-Za-z0-9_+-]*[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```$", re.DOTALL)
_TEXT_PREFIX = re.compile(r"^\s*(意图|类别|分类|intent|label)\s*[:：]\s*", re.IGNORECASE)
_WRAP_PAIRS = (
    ("「", "」"), ("『", "』"), ("“", "”"), ('"', '"'), ("'", "'"), ("‘", "’"),
    ("【", "】"), ("[", "]"), ("(", ")"), ("（", "）"), ("《", "》"), ("<", ">"),
)
_TRAILING_PUNCT = "。．.，,；;：:！!？?"
LABEL_MAX_CHARS = 64
REASON_MAX_CHARS = 500


class ParseFailure(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class EmptyOutput(ParseFailure):
    """纯文本模式下意图识别输出为空，按 EMPTY_OUTPUT 处理。"""

    def __init__(self) -> None:
        super().__init__("模型返回了空内容")


# ---- 思考内容（05 第 5 节） ----


def strip_reasoning(content: str | None, *field_reasoning: str | None) -> tuple[str, str | None]:
    """返回 (去掉思考内容的 content, 合并后的思考内容)。

    思考内容来自 message.reasoning_content / message.reasoning，以及 content 里的 <think>…</think>；
    只有结束标签时，最后一个 </think> 之前的都算思考；只有开始标签（输出被截断）时，其后的都算思考。
    """
    text = content or ""
    parts: list[str] = [r.strip() for r in field_reasoning if r and r.strip()]
    blocks = _THINK_BLOCK.findall(text)
    if blocks:
        parts.extend(b.strip() for b in blocks)
        text = _THINK_BLOCK.sub("", text)
    closes = list(_THINK_CLOSE.finditer(text))
    if closes:
        last = closes[-1]
        parts.append(_THINK_OPEN.sub("", text[: last.start()]).strip())
        text = text[last.end() :]
    else:
        opened = _THINK_OPEN.search(text)
        if opened:
            parts.append(text[opened.end() :].strip())
            text = text[: opened.start()]
    reasoning = "\n\n".join(p for p in parts if p)[:REASONING_MAX_CHARS]
    return text, reasoning or None


def preprocess(content: str) -> str:
    """去首尾空白；整段被 ```json 或 ``` 包裹时取里面的内容。"""
    text = (content or "").strip()
    match = _FENCE.match(text)
    if match:
        text = match.group(1).strip()
    return text


# ---- JSON 提取（05 第 4.2 节） ----


def _first_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _unwrap(value: Any) -> Any:
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return value


def _repair(fragment: str) -> Any:
    loader = getattr(json_repair, "loads", None)
    if loader is not None:
        return loader(fragment)
    return json_repair.repair_json(fragment, return_objects=True)


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        value = _unwrap(json.loads(text))
        if isinstance(value, dict):
            return value
    except ValueError:
        pass
    fragment = _first_object(text)
    if fragment is not None:
        try:
            value = _unwrap(json.loads(fragment))
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
    try:
        value = _unwrap(_repair(fragment if fragment is not None else text))
        if isinstance(value, dict) and value:
            return value
    except Exception:  # noqa: BLE001 - json_repair 对极端输入可能抛出任意异常
        pass
    raise ParseFailure("输出不是 JSON")


# ---- 类别规范化（05 第 4.5 节） ----


def normalize_label(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    changed = True
    while changed and text:
        changed = False
        for opening, closing in _WRAP_PAIRS:
            if len(text) >= len(opening) + len(closing) and text.startswith(opening) and text.endswith(closing):
                text = text[len(opening) : len(text) - len(closing)].strip()
                changed = True
                break
        stripped = text.rstrip(_TRAILING_PUNCT).strip()
        if stripped != text:
            text = stripped
            changed = True
    return text[:LABEL_MAX_CHARS]


# ---- 提示词里列出的意图类别（05 第 4.6 节）：人工修正只能改成这些类别 ----

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.、)）])\s*(.+?)\s*$")
_BULLET_WITH_COLON = re.compile(r"^\s*[-*]\s*([^：:\s]{1,20})\s*[：:]")   # 与演示模型相同（第 8.2 节）
_LABEL_COLON = re.compile(r"[：:]")
_WORD = re.compile(r"\w")
MAX_PROMPT_LABELS = 200


def _label_name(text: str) -> str | None:
    """列表项“类别名：说明”里的类别名，按第 4.5 节规范化；含模板变量、或不含文字（如分隔线）的不算。"""
    name = normalize_label(_LABEL_COLON.split(text, maxsplit=1)[0])
    if not name or "{{" in name or "}}" in name or not _WORD.search(name):
        return None
    return name


def _unique(names: list[str]) -> list[str]:
    return list(dict.fromkeys(names))[:MAX_PROMPT_LABELS]


def _section_labels(text: str) -> list[str]:
    """规则 1：标题（# 到 ######）里含“类别”的那一节，到下一个标题为止，每个列表项一个类别。"""
    names: list[str] = []
    in_section = False
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            if names:          # 第一个有类别的小节就够了
                break
            in_section = "类别" in heading.group(1)
            continue
        if not in_section:
            continue
        item = _LIST_ITEM.match(line)
        if item:
            name = _label_name(item.group(1))
            if name:
                names.append(name)
    return _unique(names)


def _bullet_labels(text: str) -> list[str]:
    """规则 2（没有这样的小节时）：形如“- 类别名：说明”的行，与演示模型的取法相同（第 8.2 节）。"""
    names: list[str] = []
    for line in text.splitlines():
        match = _BULLET_WITH_COLON.match(line)
        if match:
            name = _label_name(match.group(1))
            if name:
                names.append(name)
    return _unique(names)


def prompt_labels(system_prompt: str, user_template: str) -> list[str]:
    """意图识别提示词里列出的类别，按出现顺序去重；依次看系统提示词、用户消息模板，没有时为空列表。"""
    texts = [system_prompt or "", user_template or ""]
    for rule in (_section_labels, _bullet_labels):
        for text in texts:
            names = rule(text)
            if names:
                return names
    return []


def parse_confidence(value: Any) -> float | None:
    """数字或数字字符串；"85%" 视为 0.85；大于 1 且不超过 100 时除以 100；限制在 0 到 1；无法识别为 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        percent = text.endswith(("%", "％"))
        if percent:
            text = text[:-1].strip()
        try:
            number = float(text)
        except ValueError:
            return None
        if percent:
            number /= 100
    else:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    if 1 < number <= 100:
        number /= 100
    return min(1.0, max(0.0, number))


# ---- 意图识别 ----


@dataclass
class ClassifyParsed:
    label: str
    confidence: float | None
    reason: str | None
    result: dict[str, Any]


def parse_classify(content: str, field_map: dict[str, Any], output_mode: str) -> ClassifyParsed:
    text = preprocess(content)
    if output_mode == "text":
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        label = normalize_label(_TEXT_PREFIX.sub("", first))
        if not label:
            raise EmptyOutput()
        return ClassifyParsed(label, None, None, {"text": text})
    obj = extract_json_object(text)
    label_field = str(field_map.get("label") or "intent")
    raw = obj.get(label_field)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ParseFailure(f"缺少 {label_field} 字段")
    label = normalize_label(raw if not isinstance(raw, dict | list) else json.dumps(raw, ensure_ascii=False))
    if not label:
        raise ParseFailure("类别为空")
    confidence_field = field_map.get("confidence")
    reason_field = field_map.get("reason")
    confidence = parse_confidence(obj.get(confidence_field)) if confidence_field else None
    reason: str | None = None
    if reason_field and obj.get(reason_field) is not None:
        reason = str(obj.get(reason_field)).strip()[:REASON_MAX_CHARS] or None
    return ClassifyParsed(label, confidence, reason, obj)


# ---- 文本摘要 ----


@dataclass
class SummarizeParsed:
    summary: str
    key_points: list[dict[str, Any]] = field(default_factory=list)
    output_chars: int = 0
    result: dict[str, Any] = field(default_factory=dict)


_SOURCE_NUMBER = re.compile(r"^\D*?(\d+)\D*$")


def parse_sources(value: Any, segment_count: int) -> list[int]:
    items = value if isinstance(value, list) else [value]
    numbers: set[int] = set()
    for item in items:
        if isinstance(item, bool) or item is None:
            continue
        if isinstance(item, int):
            number = item
        elif isinstance(item, float) and item.is_integer():
            number = int(item)
        elif isinstance(item, str):
            match = _SOURCE_NUMBER.match(item.strip())
            if not match:
                continue
            number = int(match.group(1))
        else:
            continue
        if 1 <= number <= segment_count:
            numbers.add(number)
    return sorted(numbers)


def parse_key_points(value: Any, segment_count: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    points: list[dict[str, Any]] = []
    for element in value:
        if isinstance(element, dict):
            text = next((element.get(k) for k in ("text", "point", "content") if element.get(k)), "")
            sources = element.get("sources", element.get("source"))
        elif isinstance(element, str):
            text, sources = element, None
        else:
            continue
        text = str(text or "").strip()
        if not text:
            continue
        points.append({"text": text, "sources": parse_sources(sources, segment_count)})
    return points


def parse_summarize(content: str, field_map: dict[str, Any], output_mode: str, segment_count: int) -> SummarizeParsed:
    text = preprocess(content)
    if output_mode == "text":
        if not text:
            raise EmptyOutput()
        return SummarizeParsed(text, [], len(text), {"text": text})
    obj = extract_json_object(text)
    summary_field = str(field_map.get("summary") or "summary")
    raw = obj.get(summary_field)
    if raw is None or not str(raw).strip():
        raise ParseFailure(f"缺少 {summary_field} 字段")
    summary = str(raw).strip()
    points_field = field_map.get("key_points")
    points = parse_key_points(obj.get(points_field), segment_count) if points_field else []
    output_chars = len(summary) + sum(len(p["text"]) for p in points)
    return SummarizeParsed(summary, points, output_chars, obj)
