"""提示词渲染（05 第 2 节；08 第 10.1 节“渲染”）。"""

from __future__ import annotations

from datetime import datetime

from app.services.defaults import BUILTIN_PROMPTS
from app.services.prompt_render import (
    PromptSpec,
    RowContext,
    StageVars,
    assemble,
    has_required_input,
    plan_classify,
    render,
    variables_for,
)

ROW = RowContext(
    text="我的快递没到",
    row_number=7,
    file_name="客服.xlsx",
    row_values={"会话ID": "10023", "用户问题": "我的快递没到", "客户等级": "金卡"},
    columns=[("会话ID", "会话ID"), ("用户问题", "用户问题"), ("客户等级", "客户等级")],
)


def test_all_variables() -> None:
    stage = StageVars(text="T", text_numbered="[1] T")
    out = render(
        "{{text}}|{{text_numbered}}|{{row_number}}|{{file_name}}|{{row_json}}|{{col:客户等级}}|{{today}}", ROW, stage, "user"
    )
    parts = out.text.split("|")
    assert parts[:4] == ["T", "[1] T", "7", "客服.xlsx"]
    assert parts[4] == '{"会话ID": "10023", "用户问题": "我的快递没到", "客户等级": "金卡"}'
    assert parts[5] == "金卡"
    assert parts[6] == datetime.now().strftime("%Y-%m-%d")
    assert out.unknown == []


def test_chunk_variables_only_in_chunk_template() -> None:
    stage = StageVars(text="T", chunk_index=2, chunk_total=5)
    assert render("{{chunk_index}}/{{chunk_total}}", ROW, stage, "chunk").text == "2/5"
    out = render("{{chunk_index}}", ROW, stage, "user")
    assert out.text == "{{chunk_index}}" and out.unknown == ["{{chunk_index}}"]


def test_unknown_variable_kept_and_listed() -> None:
    out = render("前 {{ foo }} 后 {{bar}} {{foo}}", ROW, StageVars(text="T"), "user")
    assert out.text == "前 {{ foo }} 后 {{bar}} {{foo}}"
    assert out.unknown == ["{{foo}}", "{{bar}}"]


def test_missing_column_is_empty() -> None:
    assert render("[{{col:不存在}}]", ROW, StageVars(), "user").text == "[]"


def test_value_containing_variable_not_replaced_twice() -> None:
    stage = StageVars(text="原文里有 {{text}} 和 {{row_number}}")
    assert render("{{text}}", ROW, stage, "user").text == "原文里有 {{text}} 和 {{row_number}}"


def test_system_prompt_rendered() -> None:
    spec = PromptSpec.from_mapping(
        {"task_type": "classify", "system_prompt": "今天是 {{today}}，文件 {{file_name}}", "user_template": "{{text}}"}
    )
    messages = assemble(spec, spec.user_template, ROW, StageVars(text="T"), "user").messages
    assert messages[0]["role"] == "system"
    assert "客服.xlsx" in messages[0]["content"] and "{{" not in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "T"}


def test_empty_system_prompt_not_sent() -> None:
    spec = PromptSpec.from_mapping({"task_type": "classify", "system_prompt": "  ", "user_template": "{{text}}"})
    messages = assemble(spec, spec.user_template, ROW, StageVars(text="T"), "user").messages
    assert [m["role"] for m in messages] == ["user"]


def test_required_input_check() -> None:
    assert has_required_input("{{text}}")
    assert has_required_input("{{ text_numbered }}")
    assert has_required_input("{{row_json}}")
    assert has_required_input("{{col:用户问题}}")
    assert not has_required_input("只有 {{today}} 和 {{file_name}}")


def test_variables_list() -> None:
    classify = {v["name"] for v in variables_for("classify")}
    summarize = {v["name"] for v in variables_for("summarize")}
    assert "chunk_summaries" not in classify and "chunk_summaries" in summarize
    assert "col:" in classify


def test_classify_truncation_marks_item() -> None:
    spec = PromptSpec.from_mapping(BUILTIN_PROMPTS["classify.default"])
    long_row = RowContext(text="字" * 20000, row_number=1, file_name="x")
    plan = plan_classify(spec, long_row, 4096, 300)
    assert plan.truncated and plan.omitted > 0
    assert "中间省略" in plan.messages.messages[-1]["content"]


# ---- 去重键（03 第 4.7 节；08 第 10.1 节“渲染”） ----


def _spec(task_type: str, **changes: object) -> PromptSpec:
    return PromptSpec.from_mapping({**BUILTIN_PROMPTS[f"{task_type}.default"], **changes})


def test_dedupe_key_follows_rendered_messages() -> None:
    """只比较原文不够：模板引用行级变量时，相同原文得到不同的键；只用 {{text}} 时相同原文的键相同。"""
    from app.services.prompt_render import DedupeKeyer, dedupe_key

    plain = DedupeKeyer(_spec("classify"))
    row1 = RowContext(text="同样的话", row_number=1, file_name="a.csv", row_values={"B": "VIP"}, columns=[("B", "等级")])
    row2 = RowContext(text="同样的话", row_number=2, file_name="a.csv", row_values={"B": "普通"}, columns=[("B", "等级")])
    assert plain.key(row1) == plain.key(row2)
    for template in ("第 {{row_number}} 行：{{text}}", "{{text}}（等级：{{col:等级}}）", "{{row_json}}"):
        keyer = DedupeKeyer(_spec("classify", user_template=template))
        assert keyer.key(row1) != keyer.key(row2), template
    varying_system = _spec("classify", system_prompt="客户等级：{{col:等级}}")
    assert DedupeKeyer(varying_system).key(row1) != DedupeKeyer(varying_system).key(row2)
    # 缓存系统消息的快速路径与逐行完整渲染得到同一个键
    assert plain.key(row1) == dedupe_key(_spec("classify"), RowContext(
        text="同样的话", row_number=1, file_name="a.csv", row_values={"B": "VIP"}, columns=[("B", "等级")],
        today=plain.today,
    ))
