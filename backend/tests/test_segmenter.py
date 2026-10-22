"""切分与截断、分段合并（05 第 7 节；08 第 10.1 节）。"""

from __future__ import annotations

from app.services import segmenter
from app.services.defaults import BUILTIN_PROMPTS
from app.services.prompt_render import PromptSpec, RowContext, plan_summarize


def test_estimate_tokens() -> None:
    assert segmenter.estimate_tokens("") == 0
    assert segmenter.estimate_tokens("中文") == 2
    assert segmenter.estimate_tokens("abcdefg") == 2  # 7 / 3.5


def test_split_is_deterministic() -> None:
    text = "第一段。\n\n" + "这是一个比较长的句子，用来测试切分。" * 60 + "\n最后一段"
    assert segmenter.split_segments(text) == segmenter.split_segments(text)


def test_short_paragraphs_kept() -> None:
    assert segmenter.split_segments(" 第一段 \r\n\r\n第二段\r第三段") == ["第一段", "第二段", "第三段"]


def test_long_paragraph_split_by_sentence() -> None:
    sentence = "这是一个句子，" * 10 + "结束。"   # 73 字
    paragraph = sentence * 12                   # 876 字，超过 600
    segments = segmenter.split_segments(paragraph)
    assert len(segments) > 1
    assert all(len(s) <= 400 for s in segments)
    assert "".join(segments) == paragraph


def test_single_long_sentence_hard_cut() -> None:
    paragraph = "无标点" * 300  # 900 字，一个句子
    segments = segmenter.split_segments(paragraph)
    assert [len(s) for s in segments] == [400, 400, 100]


def test_numbered_text() -> None:
    assert segmenter.numbered_text(["甲", "乙"]) == "[1] 甲\n[2] 乙"


def test_truncate_within_budget() -> None:
    text = "字" * 5000
    cut = segmenter.truncate_middle(text, 300)
    assert cut.truncated
    kept = len(text) - cut.omitted
    assert kept <= 300  # 每个汉字约 1 token
    assert f"（中间省略 {cut.omitted} 字）" in cut.text
    assert cut.text.startswith("字" * 10) and cut.text.endswith("字" * 10)


def test_truncate_not_needed() -> None:
    cut = segmenter.truncate_middle("短文本", 300)
    assert not cut.truncated and cut.text == "短文本" and cut.omitted == 0


def test_pack_chunks_keeps_order_and_numbers() -> None:
    segments = [f"第 {i} 段内容" * 10 for i in range(1, 21)]
    chunks = segmenter.pack_chunks(segments, 300)
    numbers = [n for chunk in chunks for n, _ in chunk.units]
    assert numbers == sorted(numbers)
    assert set(numbers) == set(range(1, 21))
    assert all(segmenter.estimate_tokens(c.numbered) <= 300 + 20 for c in chunks)


def test_oversized_segment_split_with_same_number() -> None:
    chunks = segmenter.pack_chunks(["长" * 1000], 300)
    assert len(chunks) > 1
    assert {n for chunk in chunks for n, _ in chunk.units} == {1}


def test_group_parts_always_progresses() -> None:
    parts = ["x" * 2000] * 7
    groups = segmenter.group_parts(parts, 300)
    assert all(len(g) >= 2 for g in groups)
    assert sorted(i for g in groups for i in g) == list(range(7))
    assert len(groups) < len(parts)


def test_small_context_produces_chunks() -> None:
    spec = PromptSpec.from_mapping({**BUILTIN_PROMPTS["summarize.default"], "max_output_tokens": 500})
    text = "\n".join("用户来电反映宽带晚上经常掉线，客服登记后安排工程师上门检查。" * 6 for _ in range(30))
    plan = plan_summarize(spec, RowContext(text=text, row_number=1, file_name="x.txt"), 2048, 500)
    assert plan.single is None
    assert plan.chunk_count > 1
