"""演示模型（05 第 8 节；04 第 11 节；08 第 10.1 节“演示模型”）。"""

from __future__ import annotations

from typing import Any

from app.api.mock import _MERGE_MARK
from app.services import segmenter
from app.services.defaults import BUILTIN_PROMPTS
from app.services.prompt_render import PromptSpec, RowContext, chunk_messages, merge_messages

from .conftest import Api, LiveServer

CLASSIFY_SYSTEM = '只输出 JSON：{"intent": "类别", "confidence": 0.9, "reason": "依据"}'


def _chat(api: Api, content: str, *, system: str = CLASSIFY_SYSTEM, behavior: str = "fast",
          stream: bool = False) -> Any:
    body = {
        "model": "wenshu-demo",
        "stream": stream,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
    }
    return api.client.post("/mock/v1/chat/completions", json=body, headers={"X-Mock-Behavior": behavior})


def _summarize_spec() -> PromptSpec:
    data = next(v for v in BUILTIN_PROMPTS.values() if v["task_type"] == "summarize")
    return PromptSpec.from_mapping(data)


def test_chunk_one_is_not_a_merge_request() -> None:
    """分段模板第 1 段的开头“下面是一篇长文的第 1 部分，共 N 部分”不能被当成合并请求（05 第 8.1 节）。"""
    spec = _summarize_spec()
    text = "".join(f"第{i}句话，用户反映宽带晚上经常掉线。" for i in range(200))
    row = RowContext(text=text, row_number=1, file_name="长文.txt")
    chunk = segmenter.pack_chunks(segmenter.split_segments(text), 300)[0]
    first = chunk_messages(spec, row, chunk, 1, 3).messages[-1]["content"]
    assert "第 1 部分" in first and not _MERGE_MARK.search(first)
    merged = merge_messages(spec, row, ['{"summary": "甲"}', '{"summary": "乙"}']).messages[-1]["content"]
    assert _MERGE_MARK.search(merged)


def test_stats_and_reset(api: Api) -> None:
    api.mock_reset()
    assert api.mock_stats() == {"inflight": 0, "max_inflight": 0, "total": 0, "by_status": {}}
    first = _chat(api, "首次限流测试", behavior="rate_limit_first,fast")
    second = _chat(api, "首次限流测试", behavior="rate_limit_first,fast")
    assert (first.status_code, second.status_code) == (429, 200)
    stats = api.mock_stats()
    assert stats["total"] == 2 and stats["by_status"] == {"429": 1, "200": 1} and stats["inflight"] == 0
    assert stats["max_inflight"] >= 1
    # 内容不同就是不同的“首次请求”
    assert _chat(api, "另一段内容", behavior="rate_limit_first,fast").status_code == 429
    # _reset 清空“首次请求”的记录
    api.mock_reset()
    assert _chat(api, "首次限流测试", behavior="rate_limit_first,fast").status_code == 429
    assert api.mock_stats()["total"] == 1


def test_random_failures_only_for_engine_requests(api: Api, server: LiveServer) -> None:
    """随机故障只注入非流式的意图识别和摘要请求；流式请求（试运行）和回显请求（测试连接）从不注入。"""
    state = server.ctx.mock
    state.fail_rate = 1.0
    try:
        demo = api.demo_model_id()
        result = api.ok(api.post(f"/api/models/{demo}/test"))
        assert result["ok"] is True, result
        streamed = _chat(api, "流式请求", stream=True)
        assert streamed.status_code == 200 and "data: [DONE]" in streamed.text
        failed = _chat(api, "非流式的意图识别请求")
        assert failed.status_code in (429, 500)
        assert _chat(api, "关闭随机故障", behavior="none,fast").status_code == 200
    finally:
        state.fail_rate = 0.0
