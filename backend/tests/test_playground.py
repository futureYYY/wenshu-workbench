"""试运行：POST 返回的 SSE 流（04 第 6 节；08 第 3 节验收）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .conftest import Api


def run(api: Api, body: dict[str, Any]) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    with api.client.stream("POST", "/api/playground/run", json=body, timeout=120) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        name: str | None = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and name:
                events.append((name, json.loads(line.split(":", 1)[1].strip())))
                name = None
    return events


def draft_of(prompt: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    keys = ("task_type", "system_prompt", "user_template", "chunk_template", "merge_template", "output_mode", "field_map",
            "temperature", "max_output_tokens")
    return {**{k: prompt[k] for k in keys}, **overrides}


def test_classify_stream(api: Api) -> None:
    prompt = api.builtin_prompt("classify")
    events = run(api, {"prompt": draft_of(prompt), "model_id": api.demo_model_id(),
                       "sample": {"kind": "text", "text": "你们乱扣话费，我要投诉"}})
    names = [n for n, _ in events]
    assert names[0] == "stage" and events[0][1]["name"] == "request"
    assert "delta" in names and names[-1] == "done"
    done = events[-1][1]
    assert done["parsed"]["label"] == "投诉"   # 演示模型选中文本里出现的类别名
    assert done["parse_error"] is None and done["chunk_count"] == 1 and done["truncated"] is False
    assert "".join(d["content"] for n, d in events if n == "delta") == done["raw_output"]
    assert done["usage"]["prompt_tokens"] > 0 and done["messages"][-1]["role"] == "user"


def test_custom_category(api: Api) -> None:
    prompt = api.builtin_prompt("classify")
    system = prompt["system_prompt"].replace("- 其他：", "- 催单：催促尽快发货或处理\n- 其他：")
    events = run(api, {"prompt": draft_of(prompt, system_prompt=system), "model_id": api.demo_model_id(),
                       "sample": {"kind": "text", "text": "我要催单，怎么还没发货"}})
    assert events[-1][1]["parsed"]["label"] == "催单"


def test_parse_error_reported_in_done(api: Api) -> None:
    model = api.mock_model("试运行-坏 JSON", "bad_json,fast")
    events = run(api, {"prompt": draft_of(api.builtin_prompt("classify")), "model_id": model["id"],
                       "sample": {"kind": "text", "text": "随便一句话"}})
    done = events[-1]
    assert done[0] == "done" and done[1]["parsed"] is None
    assert done[1]["parse_error"] == "输出无法解析：输出不是 JSON"


def test_error_event(api: Api) -> None:
    model = api.mock_model("试运行-鉴权", "auth")
    events = run(api, {"prompt": draft_of(api.builtin_prompt("classify")), "model_id": model["id"],
                       "sample": {"kind": "text", "text": "随便一句话"}})
    assert events[-1][0] == "error"
    assert events[-1][1]["error_code"] == "AUTH_FAILED" and events[-1][1]["status_code"] == 401


def test_think_stream(api: Api) -> None:
    model = api.mock_model("试运行-思考", "reasoning_field,fast")
    events = run(api, {"prompt": draft_of(api.builtin_prompt("classify")), "model_id": model["id"],
                       "sample": {"kind": "text", "text": "我想办理宽带"}})
    assert any(n == "reasoning_delta" for n, _ in events)
    assert events[-1][1]["reasoning"] == "演示思考过程……"


def test_summarize_chunks_and_merge(api: Api) -> None:
    model = api.mock_model("试运行-小上下文", "fast", context_window=2048)
    prompt = draft_of(api.builtin_prompt("summarize"), max_output_tokens=500)
    text = "\n".join(f"第 {i} 段：用户反映宽带在晚上掉线，工程师上门后更换了光猫，问题已经解决。" * 4 for i in range(1, 41))
    events = run(api, {"prompt": prompt, "model_id": model["id"], "sample": {"kind": "text", "text": text}})
    stages = [d for n, d in events if n == "stage"]
    assert stages[0]["name"] == "chunk" and stages[0]["index"] == 1 and stages[0]["total"] > 1
    assert stages[-1]["name"] == "merge"
    done = events[-1][1]
    assert events[-1][0] == "done" and done["chunk_count"] == stages[0]["total"]
    assert done["parsed"]["summary"].startswith("演示摘要：合并了")


def test_row_sample(api: Api, fixture_files: dict[str, Path]) -> None:
    file = api.upload(fixture_files["intent_200.xlsx"])
    sample = {"kind": "row", "file_id": file["id"], "sheet": "对话", "header_row": 1, "text_columns": ["用户问题", "渠道"],
              "join_mode": "labeled", "row_number": 2}
    events = run(api, {"prompt": draft_of(api.builtin_prompt("classify")), "model_id": api.demo_model_id(),
                       "sample": sample})
    done = events[-1][1]
    assert "用户问题：" in done["messages"][-1]["content"] and "渠道：" in done["messages"][-1]["content"]
    rendered = api.ok(api.post("/api/prompts/render", {"prompt": draft_of(api.builtin_prompt("classify")), "sample": sample}))
    assert rendered["messages"][-1]["content"] == done["messages"][-1]["content"]
