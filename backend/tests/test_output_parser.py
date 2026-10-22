"""输出解析（05 第 4、5 节；08 第 10.1 节“输出解析”）。"""

from __future__ import annotations

import pytest

from app.services.output_parser import (
    EmptyOutput,
    ParseFailure,
    extract_json_object,
    normalize_label,
    parse_classify,
    parse_confidence,
    parse_summarize,
    preprocess,
    strip_reasoning,
)

CLASSIFY_MAP = {"label": "intent", "confidence": "confidence", "reason": "reason"}
SUMMARY_MAP = {"summary": "summary", "key_points": "key_points"}


def test_pure_json() -> None:
    parsed = parse_classify('{"intent": "咨询", "confidence": 0.9, "reason": "询问价格"}', CLASSIFY_MAP, "json")
    assert (parsed.label, parsed.confidence, parsed.reason) == ("咨询", 0.9, "询问价格")
    assert parsed.result == {"intent": "咨询", "confidence": 0.9, "reason": "询问价格"}


def test_code_fence() -> None:
    assert preprocess('```json\n{"intent": "投诉"}\n```') == '{"intent": "投诉"}'
    assert parse_classify('```\n{"intent": "投诉"}\n```', CLASSIFY_MAP, "json").label == "投诉"


def test_json_with_surrounding_text() -> None:
    text = '好的，结果如下：{"intent": "办理", "reason": "说明里有 } 和 { 符号"} 以上。'
    parsed = parse_classify(text, CLASSIFY_MAP, "json")
    assert parsed.label == "办理"
    assert parsed.reason == "说明里有 } 和 { 符号"


def test_repairable_json() -> None:
    assert extract_json_object('{"intent": "建议", "confidence": 0.8')["intent"] == "建议"


def test_single_object_array() -> None:
    assert extract_json_object('[{"intent": "其他"}]') == {"intent": "其他"}


def test_not_json() -> None:
    with pytest.raises(ParseFailure) as info:
        parse_classify("好的，我认为这是咨询", CLASSIFY_MAP, "json")
    assert info.value.reason == "输出不是 JSON"


def test_missing_label_uses_real_field_name() -> None:
    with pytest.raises(ParseFailure) as info:
        parse_classify('{"category": "咨询"}', CLASSIFY_MAP, "json")
    assert info.value.reason == "缺少 intent 字段"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0.9, 0.9), ("0.9", 0.9), ("85%", 0.85), (85, 0.85), ("高", None), (True, None), (150, 1.0), (-1, 0.0), (None, None)],
)
def test_confidence(raw: object, expected: float | None) -> None:
    assert parse_confidence(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  物流   查询 ", "物流 查询"),
        ("「退款咨询」", "退款咨询"),
        ("『投诉』", "投诉"),
        ("“建议”", "建议"),
        ('"办理"', "办理"),
        ("'其他'", "其他"),
        ("‘咨询’", "咨询"),
        ("【物流查询】", "物流查询"),
        ("[物流查询]", "物流查询"),
        ("(物流查询)", "物流查询"),
        ("（物流查询）", "物流查询"),
        ("《物流查询》", "物流查询"),
        ("<物流查询>", "物流查询"),
        ("物流查询。", "物流查询"),
        ("物流查询！？", "物流查询"),
        ("「物流查询」。", "物流查询"),
        ("a" * 80, "a" * 64),
    ],
)
def test_label_normalization(raw: str, expected: str) -> None:
    assert normalize_label(raw) == expected


def test_empty_label_is_failure() -> None:
    with pytest.raises(ParseFailure) as info:
        parse_classify('{"intent": "「」"}', CLASSIFY_MAP, "json")
    assert info.value.reason == "类别为空"


def test_think_block_removed() -> None:
    content, reasoning = strip_reasoning('<think>先想一想</think>{"intent": "咨询"}')
    assert content == '{"intent": "咨询"}'
    assert reasoning == "先想一想"


def test_only_closing_think_tag() -> None:
    content, reasoning = strip_reasoning("这里是思考过程</think>结果")
    assert content == "结果"
    assert reasoning == "这里是思考过程"


def test_reasoning_content_field() -> None:
    content, reasoning = strip_reasoning('{"intent": "咨询"}', "字段里的思考")
    assert content == '{"intent": "咨询"}'
    assert reasoning == "字段里的思考"


def test_key_points_variants() -> None:
    text = (
        '{"summary": "主旨", "key_points": ['
        '"字符串要点", {"text": "对象要点", "sources": [3, 1, 3]}, {"point": "point 字段", "source": 2},'
        '{"content": "content 字段", "sources": ["4", 99, 0]}, {"text": ""}]}'
    )
    parsed = parse_summarize(text, SUMMARY_MAP, "json", segment_count=5)
    assert parsed.summary == "主旨"
    assert parsed.key_points == [
        {"text": "字符串要点", "sources": []},
        {"text": "对象要点", "sources": [1, 3]},
        {"text": "point 字段", "sources": [2]},
        {"text": "content 字段", "sources": [4]},
    ]
    assert parsed.output_chars == len("主旨") + sum(len(p["text"]) for p in parsed.key_points)


def test_summary_missing() -> None:
    with pytest.raises(ParseFailure):
        parse_summarize('{"key_points": []}', SUMMARY_MAP, "json", 3)


def test_text_mode_prefix_removed() -> None:
    for text in ("意图：咨询", "类别: 咨询", "分类：咨询", "Intent: 咨询", "LABEL：咨询"):
        parsed = parse_classify(f"\n{text}\n多余的一行", CLASSIFY_MAP, "text")
        assert parsed.label == "咨询"
        assert parsed.confidence is None and parsed.reason is None


def test_text_mode_empty_is_empty_output() -> None:
    with pytest.raises(EmptyOutput):
        parse_classify("意图：", CLASSIFY_MAP, "text")


def test_text_mode_summary() -> None:
    parsed = parse_summarize("  整段就是摘要  ", SUMMARY_MAP, "text", 3)
    assert parsed.summary == "整段就是摘要"
    assert parsed.key_points == []
    assert parsed.result == {"text": "整段就是摘要"}
