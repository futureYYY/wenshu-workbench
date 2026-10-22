"""任务引擎（02 第 5 节；05 第 6、7 节；03 第 6、8 节；08 第 4 节验收、第 10.1 节“引擎”）。

全部使用演示模型（WENSHU_MOCK_FAIL_RATE=0），故障由请求头 X-Mock-Behavior 控制。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .conftest import Api, LiveServer, unique_lines

DEMO_LABELS_ORDER = ("咨询", "办理", "投诉", "建议", "其他")    # 内置提示词列出的类别
DEMO_LABELS = set(DEMO_LABELS_ORDER)


def _wait_mock_idle(api: Api, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if api.mock_stats()["inflight"] == 0:
            return
        time.sleep(0.1)
    raise AssertionError("演示模型还有进行中的请求")


def test_basic_classify_job(api: Api, fast_model: dict[str, Any]) -> None:
    file = api.paste(unique_lines("基础", 30))
    job = api.create_job(file, model_id=fast_model["id"], concurrency=5, limit=None)
    assert job["status"] == "running" and job["started_at"]
    assert job["model_name"] == "测试-快速" and job["prompt_name"] == "默认意图识别"
    assert job["source"]["columns"] == [{"key": "text", "title": "文本", "letter": None, "index": 0}]
    done = api.wait_job(job["id"])
    progress = done["progress"]
    assert progress["succeeded"] == 30 and progress["failed"] == 0 and progress["percent"] == 100.0
    assert done["finished_at"] and done["usage"]["prompt_tokens"] > 0
    categories = api.ok(api.get(f"/api/jobs/{job['id']}/categories"))
    assert sum(c["count"] for c in categories["items"]) == 30 and categories["failed"] == 0
    assert all(0 <= c["color_index"] <= 10 for c in categories["items"])
    assert done["categories"] == categories["items"]
    items = api.items(job["id"])
    assert {i["label"] for i in items} <= DEMO_LABELS
    assert all(i["attempts"] == 1 and i["status"] == "succeeded" for i in items)
    detail = api.ok(api.get(f"/api/jobs/{job['id']}/items/{items[0]['id']}"))
    assert detail["model_used"] == "wenshu-demo" and detail["messages"][-1]["content"].endswith(detail["input_text"])
    assert detail["attempt_log"][-1]["message"] == "成功"


def test_estimate_limit_start_row_and_skipped(api: Api, fast_model: dict[str, Any]) -> None:
    file = api.paste("预估甲\n\n预估乙\n预估丙\n\n预估丁")
    body = api.job_body(file, model_id=fast_model["id"], limit=2, start_row=2)
    estimate = api.ok(api.post("/api/jobs/estimate", body))
    assert estimate["item_count"] == 2 and estimate["skipped_empty"] == 1
    assert estimate["request_count"] == 2 and len(estimate["est_seconds"]) == 2
    job = api.ok(api.post("/api/jobs", body), 201)
    assert job["progress"]["total"] == 3 and job["progress"]["skipped"] == 1
    api.wait_job(job["id"])
    items = api.items(job["id"])
    assert [(i["row_number"], i["status"]) for i in items] == [(2, "skipped"), (3, "succeeded"), (4, "succeeded")]


def test_no_items(api: Api, fast_model: dict[str, Any]) -> None:
    file = api.paste("只有一行")
    body = api.job_body(file, model_id=fast_model["id"], start_row=5)
    api.error(api.post("/api/jobs/estimate", body), 422, "NO_ITEMS")
    api.error(api.post("/api/jobs", body), 422, "NO_ITEMS")


def test_dedupe_followers(api: Api, fast_model: dict[str, Any]) -> None:
    file = api.paste("去重文本A\n去重文本A\n去重文本B\n去重文本A")
    estimate = api.ok(api.post("/api/jobs/estimate", api.job_body(file, model_id=fast_model["id"])))
    assert estimate["duplicate_count"] == 2 and estimate["request_count"] == 2
    no_dedupe = api.ok(api.post("/api/jobs/estimate", api.job_body(file, model_id=fast_model["id"], dedupe=False)))
    assert no_dedupe["duplicate_count"] == 0

    job = api.create_job(file, model_id=fast_model["id"])
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 4
    items = api.items(job["id"])
    leader = items[0]
    followers = [i for i in items if i["dedup_of"] == leader["id"]]
    assert len(followers) == 2
    assert all(f["label"] == leader["label"] and f["attempts"] == 0 and f["status"] == "succeeded" for f in followers)


def test_task_concurrency_limit(api: Api) -> None:
    model = api.mock_model("测试-并发", concurrency_cap=20)
    _wait_mock_idle(api)
    api.mock_reset()
    file = api.paste(unique_lines("并发", 60))
    job = api.create_job(file, model_id=model["id"], concurrency=20, limit=None)
    max_tracks = 0
    while True:
        tracks = api.ok(api.get(f"/api/jobs/{job['id']}/tracks"))["items"]
        max_tracks = max(max_tracks, len(tracks))
        if api.job(job["id"])["status"] == "completed":
            break
        time.sleep(0.1)
    stats = api.mock_stats()
    assert stats["max_inflight"] <= 20
    assert stats["max_inflight"] >= 10
    assert stats["total"] == 60 and stats["by_status"] == {"200": 60}   # 结果落库前不会被重复派发
    assert 0 < max_tracks <= 20


def test_model_level_shared_cap(api: Api) -> None:
    model = api.mock_model("测试-共享上限", concurrency_cap=8)
    _wait_mock_idle(api)
    api.mock_reset()
    first = api.create_job(api.paste(unique_lines("共享一", 30)), model_id=model["id"], concurrency=10)
    second = api.create_job(api.paste(unique_lines("共享二", 30)), model_id=model["id"], concurrency=10)
    api.wait_job(first["id"])
    api.wait_job(second["id"])
    stats = api.mock_stats()
    assert stats["max_inflight"] <= 8
    assert stats["max_inflight"] >= 6


def test_pause_and_resume(api: Api) -> None:
    model = api.mock_model("测试-暂停")
    file = api.paste(unique_lines("暂停", 40))
    job = api.create_job(file, model_id=model["id"], concurrency=5, limit=None)
    deadline = time.monotonic() + 30
    while api.job(job["id"])["progress"]["succeeded"] < 5:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    paused = api.ok(api.post(f"/api/jobs/{job['id']}/pause"))
    assert paused["status"] == "paused" and paused["status_reason"] == "已手动暂停"
    assert paused["status_reason_code"] == "user_pause"
    api.error(api.post(f"/api/jobs/{job['id']}/pause"), 409, "JOB_STATE_CONFLICT")
    idle = api.wait_job(job["id"], ("paused",))
    assert idle["progress"]["running"] == 0
    _wait_mock_idle(api)
    requests_before = api.mock_stats()["total"]
    time.sleep(1.5)
    assert api.mock_stats()["total"] == requests_before  # 暂停后不再派发
    assert api.job(job["id"])["status"] == "paused"      # 暂停后不自动完成
    resumed = api.ok(api.post(f"/api/jobs/{job['id']}/resume"))
    assert resumed["status"] == "running" and resumed["status_reason_code"] is None
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 40 and done["status_reason"] == ""
    assert done["status_reason_code"] is None


def test_cancel(api: Api) -> None:
    model = api.mock_model("测试-取消")
    job = api.create_job(api.paste(unique_lines("取消", 30)), model_id=model["id"], concurrency=3, limit=None)
    time.sleep(1.0)
    cancelled = api.ok(api.post(f"/api/jobs/{job['id']}/cancel"))
    assert cancelled["status"] == "cancelled" and cancelled["finished_at"]
    done = api.wait_job(job["id"], ("cancelled",))
    assert done["progress"]["pending"] > 0
    deadline = time.monotonic() + 5  # 被打断的条目经写入协程放回 pending
    while api.items(job["id"], status="running") and time.monotonic() < deadline:
        time.sleep(0.1)
    assert api.items(job["id"], status="running") == []
    api.error(api.post(f"/api/jobs/{job['id']}/resume"), 409, "JOB_STATE_CONFLICT")
    api.error(api.post(f"/api/jobs/{job['id']}/cancel"), 409, "JOB_STATE_CONFLICT")
    assert api.delete(f"/api/jobs/{job['id']}").status_code == 204
    api.error(api.get(f"/api/jobs/{job['id']}"), 404, "NOT_FOUND")


def test_rate_limit_first_retries(api: Api) -> None:
    model = api.mock_model("测试-限流", "rate_limit_first,fast")
    job = api.create_job(api.paste(unique_lines("限流", 5)), model_id=model["id"], concurrency=5, dedupe=False)
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 5
    items = api.items(job["id"])
    assert all(i["attempts"] == 2 for i in items)
    detail = api.ok(api.get(f"/api/jobs/{job['id']}/items/{items[0]['id']}"))
    first, second = detail["attempt_log"][-2:]
    assert first["status_code"] == 429 and first["error_code"] == "RATE_LIMITED" and "秒后重试" in first["message"]
    assert second["status_code"] == 200 and second["message"] == "成功"


def test_rate_limit_first_with_dedupe(api: Api) -> None:
    """08 第 4 节：开启去重时，主条目 attempts = 2，跟随条目为 0。"""
    model = api.mock_model("测试-限流去重", "rate_limit_first,fast")
    job = api.create_job(api.paste("限流去重甲\n限流去重甲\n限流去重乙"), model_id=model["id"], concurrency=2)
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 3
    items = api.items(job["id"])
    leaders = [i for i in items if i["dedup_of"] is None]
    followers = [i for i in items if i["dedup_of"] is not None]
    assert len(followers) == 1 and followers[0]["attempts"] == 0
    assert all(i["attempts"] == 2 for i in leaders)


def test_auth_failure_pauses_then_resume_after_fix(api: Api) -> None:
    model = api.mock_model("测试-鉴权", "auth")
    job = api.create_job(api.paste(unique_lines("鉴权", 10)), model_id=model["id"], concurrency=2)
    paused = api.wait_job(job["id"], ("paused",))
    assert paused["status_reason"] == "模型密钥无效或无权限（HTTP 401）"
    assert paused["status_reason_code"] == "auth_failed"
    assert paused["progress"]["failed"] == 0
    assert api.items(job["id"], status="failed") == []   # 触发的条目回到 pending，不计失败
    assert len(api.items(job["id"], status="pending")) == 10
    api.ok(api.patch(f"/api/models/{model['id']}", {"extra_headers": {"X-Mock-Behavior": "fast"}}))
    api.ok(api.post(f"/api/jobs/{job['id']}/resume"))
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 10


def test_model_not_found_pauses(api: Api) -> None:
    model = api.mock_model("测试-模型不存在", "not_found")
    job = api.create_job(api.paste(unique_lines("模型不存在", 3)), model_id=model["id"], concurrency=1)
    paused = api.wait_job(job["id"], ("paused",))
    assert paused["status_reason"] == "模型“wenshu-demo”不存在，或接口地址不对（HTTP 404）"
    assert paused["status_reason_code"] == "model_not_found"
    assert paused["progress"]["failed"] == 0


def test_bad_json_parse_error(api: Api) -> None:
    model = api.mock_model("测试-坏 JSON", "bad_json,fast")
    job = api.create_job(api.paste(unique_lines("坏JSON", 2)), model_id=model["id"], dedupe=False)
    done = api.wait_job(job["id"])
    assert done["progress"]["failed"] == 2
    item = api.items(job["id"])[0]
    assert item["error_code"] == "PARSE_ERROR" and item["attempts"] == 2
    detail = api.ok(api.get(f"/api/jobs/{job['id']}/items/{item['id']}"))
    assert detail["raw_output"] == "好的，我认为这是咨询"
    assert [e["phase"] for e in detail["attempt_log"]] == ["request", "parse_repair"]

    # 重试失败项：修好模型后重新排队
    api.ok(api.patch(f"/api/models/{model['id']}", {"extra_headers": {"X-Mock-Behavior": "fast"}}))
    retried = api.ok(api.post(f"/api/jobs/{job['id']}/retry-failed"))
    assert retried["status"] == "running" and retried["progress"]["failed"] == 0
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 2
    api.error(api.post(f"/api/jobs/{job['id']}/retry-failed"), 409, "JOB_STATE_CONFLICT")


def test_circuit_breaker(api: Api) -> None:
    model = api.mock_model("测试-熔断", "server_error,fast")
    job = api.create_job(api.paste(unique_lines("熔断", 30)), model_id=model["id"], concurrency=1, max_retries=0)
    paused = api.wait_job(job["id"], ("paused",))
    assert paused["status_reason"] == "连续 10 条请求失败，最后一次：模型服务出错（HTTP 500）"
    assert paused["status_reason_code"] == "circuit_breaker"
    assert paused["progress"]["failed"] == 10   # 触发熔断的条目保持 failed
    assert all(i["error_code"] == "SERVER_ERROR" for i in api.items(job["id"], status="failed"))


def test_context_too_long_fallback(api: Api) -> None:
    model = api.mock_model("测试-上下文超长", "context,fast")
    job = api.create_job(api.paste(unique_lines("超长", 1)), model_id=model["id"], max_retries=0)
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    assert item["status"] == "failed" and item["error_code"] == "CONTEXT_TOO_LONG"
    assert item["attempts"] == 3  # 原请求 + 缩小预算后 2 次


def test_empty_output_retried_then_failed(api: Api) -> None:
    model = api.mock_model("测试-空内容", "empty,fast")
    job = api.create_job(api.paste(unique_lines("空内容", 1)), model_id=model["id"], max_retries=1)
    api.wait_job(job["id"], timeout=30)
    item = api.items(job["id"])[0]
    assert item["error_code"] == "EMPTY_OUTPUT" and item["attempts"] == 2


def test_reasoning_saved(api: Api) -> None:
    for behavior in ("think,fast", "reasoning_field,fast"):
        model = api.mock_model(f"测试-{behavior}", behavior)
        job = api.create_job(api.paste(unique_lines(behavior, 2)), model_id=model["id"])
        api.wait_job(job["id"])
        item = api.items(job["id"])[0]
        detail = api.ok(api.get(f"/api/jobs/{job['id']}/items/{item['id']}"))
        assert detail["status"] == "succeeded" and detail["label"] in DEMO_LABELS
        assert detail["reasoning"] == "演示思考过程……"


def test_rerun_single_item(api: Api, fast_model: dict[str, Any]) -> None:
    file = api.paste("重跑A\n重跑A\n\n重跑B")
    job = api.create_job(file, model_id=fast_model["id"])
    api.wait_job(job["id"])
    items = api.items(job["id"])
    leader, follower, skipped, other = items
    rerun = api.ok(api.post(f"/api/jobs/{job['id']}/items/{other['id']}/rerun"))
    assert rerun["status"] == "pending"
    done = api.wait_job(job["id"])
    assert done["status"] == "completed" and done["progress"]["succeeded"] == 3
    assert api.ok(api.get(f"/api/jobs/{job['id']}/items/{other['id']}"))["attempts"] == 2
    detached = api.ok(api.post(f"/api/jobs/{job['id']}/items/{follower['id']}/rerun"))
    assert detached["dedup_of"] is None
    api.wait_job(job["id"])
    api.error(api.post(f"/api/jobs/{job['id']}/items/{skipped['id']}/rerun"), 409, "JOB_STATE_CONFLICT")
    assert leader["status"] == "succeeded"


def test_item_patch(api: Api, fast_model: dict[str, Any]) -> None:
    job = api.create_job(api.paste("人工修正测试"), model_id=fast_model["id"])
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    # 只能改成提示词里列出的类别（05 第 4.6 节），完整规则见 test_review.py
    target = next(name for name in DEMO_LABELS_ORDER if name != item["label"])
    patched = api.ok(api.patch(f"/api/jobs/{job['id']}/items/{item['id']}", {"manual_label": target, "reviewed": True}))
    assert patched["manual_label"] == target and patched["effective_label"] == target and patched["reviewed"]
    assert [i["id"] for i in api.items(job["id"], label=target)] == [item["id"]]
    reverted = api.ok(api.patch(f"/api/jobs/{job['id']}/items/{item['id']}", {"manual_label": None}))
    assert reverted["manual_label"] is None and reverted["effective_label"] == item["label"]


def test_item_filters_and_order(api: Api, fast_model: dict[str, Any]) -> None:
    job = api.create_job(api.paste("筛选A 投诉\n\n筛选B 咨询\n筛选C"), model_id=fast_model["id"])
    api.wait_job(job["id"])
    assert [i["status"] for i in api.items(job["id"], status="skipped")] == ["skipped"]
    assert len(api.items(job["id"], q="筛选B")) == 1
    seqs = [i["seq"] for i in api.items(job["id"], order="-seq")]
    assert seqs == sorted(seqs, reverse=True)
    page = api.ok(api.get(f"/api/jobs/{job['id']}/items", params={"limit": 2, "offset": 1}))
    assert page["total"] == 4 and [i["seq"] for i in page["items"]] == [2, 3]


# 一行 2 万字（粘贴时每行是一条），按句末标点切成小段（05 第 7.2 节）。句子要够长：演示模型的分段摘要取
# 第一句（最多 80 字）和分句（最多 40 字），各段摘要合起来超过合并预算，才会发生多轮合并
_LONG_SENTENCE = (
    "用户来电反映家里的宽带在晚上七点到十一点之间经常出现掉线和网速明显变慢的情况并且已经持续了将近两个星期"
    "严重影响孩子上网课和自己居家办公，客服登记后安排工程师上门检查线路并承诺三个工作日内给出处理结果。"
)
LONG_SUMMARY_TEXT = "".join(f"第{i}次来电{_LONG_SENTENCE}" for i in range(300))[:20000]


def test_summarize_long_text_chunks(api: Api) -> None:
    """08 第 4 节：上下文 4096、内置摘要模板，对 2 万字文本做摘要：分段，发生多轮合并，结果有要点和段落编号。"""
    model = api.mock_model("测试-小上下文", "fast", context_window=4096)
    job = api.create_job(api.paste(LONG_SUMMARY_TEXT), task_type="summarize", model_id=model["id"])
    done = api.wait_job(job["id"], timeout=120)
    item = api.items(job["id"])[0]
    assert done["progress"]["succeeded"] == 1, item
    assert item["chunk_count"] > 1
    detail = api.ok(api.get(f"/api/jobs/{job['id']}/items/{item['id']}"))
    assert detail["summary"].startswith("演示摘要")
    assert detail["key_points"] and all(p["sources"] for p in detail["key_points"])
    assert all(1 <= s <= len(detail["segments"]) for p in detail["key_points"] for s in p["sources"])
    phases = [e["phase"] for e in detail["attempt_log"]]
    assert phases.count("merge") > 1, phases     # 多轮合并
    assert done["compression"]["ratio"] and done["compression"]["output_chars"] > 0


def test_summarize_context_too_small(api: Api) -> None:
    """上下文 2048 时内置摘要模板的输入预算不到 256：条目以 CONTEXT_TOO_SMALL 失败（预期行为）。"""
    model = api.mock_model("测试-上下文过小", "fast", context_window=2048)
    job = api.create_job(api.paste(LONG_SUMMARY_TEXT), task_type="summarize", model_id=model["id"])
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    assert item["status"] == "failed" and item["error_code"] == "CONTEXT_TOO_SMALL"


def test_summarize_short_text(api: Api, fast_model: dict[str, Any]) -> None:
    job = api.create_job(api.paste("第一句话。第二句话，补充说明。"), task_type="summarize", model_id=fast_model["id"])
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    assert item["status"] == "succeeded" and item["chunk_count"] == 1
    assert item["summary_preview"].startswith("演示摘要：") and item["compression_ratio"] is not None


def test_job_list_and_patch(api: Api, fast_model: dict[str, Any]) -> None:
    job = api.create_job(api.paste("列表测试"), model_id=fast_model["id"], name="自定义任务名")
    api.wait_job(job["id"])
    listing = api.ok(api.get("/api/jobs", params={"q": "自定义任务", "status": "completed,paused"}))
    assert [j["id"] for j in listing["items"]] == [job["id"]]
    renamed = api.ok(api.patch(f"/api/jobs/{job['id']}", {"name": "改过的名字", "concurrency": 3}))
    assert renamed["name"] == "改过的名字" and renamed["concurrency"] == 3
    api.error(api.post(f"/api/jobs/{job['id']}/pause"), 409, "JOB_STATE_CONFLICT")


def test_shutdown_endpoint_pauses_in_dev(api: Api, server: LiveServer) -> None:
    """开发模式下 /api/system/shutdown 只暂停任务，不退出进程（会话级测试服务就是开发模式）。"""
    model = api.mock_model("关机测试")
    job = api.create_job(api.paste(unique_lines("关机", 20)), model_id=model["id"], concurrency=2, limit=None)
    time.sleep(0.5)
    result = api.ok(api.post("/api/system/shutdown"), 202)
    assert result["paused_jobs"] == 1
    paused = api.wait_job(job["id"], ("paused",))
    assert paused["status_reason"] == "程序退出时任务未完成，可以继续"
    assert paused["status_reason_code"] == "shutdown"
    assert api.get("/api/health").status_code == 200  # 进程还在
    assert server.thread is not None and server.thread.is_alive()


def test_restart_recovery(tmp_path: Path) -> None:
    """运行中结束进程再启动：任务变为已暂停且原因正确；继续后完成，已成功的条目不重复请求。

    用内置演示模型（base_url 为 demo://local，每次调用都解析成当前端口）：重启后端口变了，它仍然可用，和真实
    使用时换了端口的情况一样。mock_model 建的自定义模型写死了第一次启动的端口，重启后会连不上。"""
    data_dir = tmp_path / "data"
    first = LiveServer(data_dir).start()
    client = Api(first)
    demo_id = client.demo_model_id()
    job = client.create_job(client.paste(unique_lines("恢复", 30)), model_id=demo_id, concurrency=3, limit=None)
    deadline = time.monotonic() + 30
    while client.job(job["id"])["progress"]["succeeded"] < 5:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    client.client.close()
    first.stop()

    # 模拟崩溃：进程没来得及收尾，任务还是 running，有条目停在 running
    with sqlite3.connect(data_dir / "wenshu.db") as conn:
        conn.execute(
            "UPDATE jobs SET status = 'running', status_reason = '', status_reason_code = NULL WHERE id = ?",
            (job["id"],),
        )
        conn.execute(
            "UPDATE job_items SET status = 'running' WHERE id IN "
            "(SELECT id FROM job_items WHERE job_id = ? AND status = 'pending' ORDER BY seq LIMIT 2)",
            (job["id"],),
        )
        succeeded_before = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT id, attempts FROM job_items WHERE job_id = ? AND status = 'succeeded'", (job["id"],)
            )
        }

    second = LiveServer(data_dir).start()
    try:
        client = Api(second)
        recovered = client.job(job["id"])
        assert recovered["status"] == "paused"
        assert recovered["status_reason"] == "程序退出时任务未完成，可以继续"
        assert recovered["status_reason_code"] == "shutdown"
        assert recovered["progress"]["succeeded"] == len(succeeded_before)
        assert client.items(job["id"], status="running") == []
        client.ok(client.post(f"/api/jobs/{job['id']}/resume"))
        done = client.wait_job(job["id"])
        assert done["progress"]["succeeded"] == 30
        after = {i["id"]: i["attempts"] for i in client.items(job["id"])}
        assert all(after[item_id] == attempts for item_id, attempts in succeeded_before.items())
        client.client.close()
    finally:
        second.stop()


# ---- 审核版新增（08 第 4 节验收、第 10.1 节“引擎”） ----


def _wait_inflight(api: Api, count: int, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while api.mock_stats()["inflight"] < count:
        assert time.monotonic() < deadline, f"演示模型没有达到 {count} 个进行中的请求"
        time.sleep(0.02)


def test_resume_while_draining_reuses_runner(api: Api) -> None:
    """并发 5，暂停后立刻继续（暂停前派发的条目还没做完）：max_inflight 不超过 5，没有条目被处理两次。"""
    model = api.mock_model("测试-收尾时继续")
    api.mock_reset()
    job = api.create_job(api.paste(unique_lines("收尾", 20)), model_id=model["id"], concurrency=5, limit=None,
                         dedupe=False)
    _wait_inflight(api, 5)
    api.ok(api.post(f"/api/jobs/{job['id']}/pause"))
    resumed = api.ok(api.post(f"/api/jobs/{job['id']}/resume"))
    assert resumed["status"] == "running"
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 20
    stats = api.mock_stats()
    assert stats["max_inflight"] <= 5, stats
    assert stats["total"] == 20, stats
    assert all(i["attempts"] == 1 for i in api.items(job["id"]))


def test_paused_job_stays_paused_when_drained(api: Api) -> None:
    """暂停期间恰好做完：保持 paused，不悄悄变成 completed；继续时转为 completed（03 第 6.1 节）。"""
    model = api.mock_model("测试-暂停期间做完")
    api.mock_reset()
    job = api.create_job(api.paste(unique_lines("做完", 3)), model_id=model["id"], concurrency=5, limit=None)
    _wait_inflight(api, 3)
    api.ok(api.post(f"/api/jobs/{job['id']}/pause"))
    paused = api.wait_job(job["id"], ("paused",))
    assert paused["progress"]["succeeded"] == 3 and paused["progress"]["pending"] == 0
    time.sleep(0.5)
    assert api.job(job["id"])["status"] == "paused"
    resumed = api.ok(api.post(f"/api/jobs/{job['id']}/resume"))
    assert resumed["status"] == "completed" and resumed["finished_at"]
    assert resumed["status_reason"] == "" and resumed["status_reason_code"] is None


def test_resume_while_draining_without_pending(api: Api) -> None:
    """全部条目都已派发、还没做完时暂停再继续：库里只剩 running 的条目，任务写为 running 并复用执行器，
    等这几条做完后再完成，不能提前置为 completed（02 第 5.4 节；03 第 6.1 节）。"""
    model = api.mock_model("测试-收尾时继续-无待处理", "slow")   # 每条 1.5–6 秒，暂停、继续时一定还在处理
    api.mock_reset()
    job = api.create_job(api.paste(unique_lines("无待处理", 3)), model_id=model["id"], concurrency=5, limit=None)
    _wait_inflight(api, 3)
    api.ok(api.post(f"/api/jobs/{job['id']}/pause"))
    resumed = api.ok(api.post(f"/api/jobs/{job['id']}/resume"))
    assert resumed["status"] == "running" and resumed["finished_at"] is None
    done = api.wait_job(job["id"])
    assert done["progress"]["succeeded"] == 3 and done["finished_at"]
    assert api.mock_stats()["total"] == 3                      # 没有条目被重新派发
    assert all(i["attempts"] == 1 for i in api.items(job["id"]))


def test_rerun_while_running(api: Api) -> None:
    """运行中对一条已成功的条目单条重新处理：它被重新请求一次，任务最终正常完成，不会一直停在运行中。"""
    model = api.mock_model("测试-运行中重跑")
    api.mock_reset()
    job = api.create_job(api.paste(unique_lines("运行中重跑", 20)), model_id=model["id"], concurrency=2, limit=None,
                         dedupe=False)
    deadline = time.monotonic() + 30
    while not api.items(job["id"], status="succeeded"):
        assert time.monotonic() < deadline
        time.sleep(0.05)
    target = api.items(job["id"], status="succeeded")[0]
    assert api.job(job["id"])["status"] == "running"
    rerun = api.ok(api.post(f"/api/jobs/{job['id']}/items/{target['id']}/rerun"))
    assert rerun["status"] in ("pending", "running")   # 执行器被唤醒后可能已经捡走了这条
    done = api.wait_job(job["id"], timeout=120)
    assert done["status"] == "completed" and done["progress"]["succeeded"] == 20
    detail = api.ok(api.get(f"/api/jobs/{job['id']}/items/{target['id']}"))
    assert detail["status"] == "succeeded" and detail["attempts"] == 2
    assert api.mock_stats()["total"] == 21


def test_rerun_running_item_conflict(api: Api) -> None:
    """正在处理的条目单条重跑返回 409（04 第 8.2 节）。"""
    model = api.mock_model("测试-处理中重跑", "slow")
    job = api.create_job(api.paste(unique_lines("处理中", 3)), model_id=model["id"], concurrency=1, limit=None)
    deadline = time.monotonic() + 15
    while not api.items(job["id"], status="running"):
        assert time.monotonic() < deadline
        time.sleep(0.05)
    running = api.items(job["id"], status="running")[0]
    api.error(api.post(f"/api/jobs/{job['id']}/items/{running['id']}/rerun"), 409, "JOB_STATE_CONFLICT")
    api.ok(api.post(f"/api/jobs/{job['id']}/cancel"))


def test_unexpected_exception_is_isolated(api: Api, monkeypatch: Any) -> None:
    """某一条抛出意外异常不影响其他条目：它以 INTERNAL_ERROR 失败，其余照常完成。"""
    from app.services.job_engine import processor as processor_module

    original = processor_module.ItemProcessor.process

    async def flaky(self: Any, item: Any, meta: Any = None) -> Any:
        if "炸弹" in item.input_text:
            raise RuntimeError("测试用的意外异常")
        return await original(self, item, meta)

    monkeypatch.setattr(processor_module.ItemProcessor, "process", flaky)
    model = api.mock_model("测试-意外异常", "fast")
    job = api.create_job(api.paste("正常一\n炸弹\n正常二\n正常三"), model_id=model["id"], concurrency=2)
    done = api.wait_job(job["id"])
    assert done["status"] == "completed"
    assert done["progress"]["succeeded"] == 3 and done["progress"]["failed"] == 1
    failed = api.items(job["id"], status="failed")
    assert [i["error_code"] for i in failed] == ["INTERNAL_ERROR"]


def _prompt_copy(api: Api, task_type: str, name: str, **changes: Any) -> dict[str, Any]:
    builtin = api.builtin_prompt(task_type)
    copy = api.ok(api.post("/api/prompts", {"copy_from_id": builtin["id"], "name": name}), 201)
    body = {
        k: copy[k]
        for k in ("task_type", "name", "system_prompt", "user_template", "chunk_template", "merge_template",
                  "output_mode", "field_map", "temperature", "max_output_tokens")
    }
    return api.ok(api.put(f"/api/prompts/{copy['id']}", {**body, **changes}))


def test_output_truncated_retry_rules(api: Api) -> None:
    """05 第 6.1 节：输出被截断且解析失败时，有效最大输出小于 8192 才翻倍重试 1 次；已经 ≥ 8192 时不重试。"""
    model = api.mock_model("测试-输出截断", "bad_json,truncate,fast")
    job = api.create_job(api.paste("截断测试甲"), model_id=model["id"], max_retries=0)
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    assert item["error_code"] == "OUTPUT_TRUNCATED" and item["attempts"] == 2

    big = _prompt_copy(api, "classify", "最大输出 8192", max_output_tokens=8192)
    job = api.create_job(api.paste("截断测试乙"), model_id=model["id"], prompt_id=big["id"], max_retries=0)
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    assert item["error_code"] == "OUTPUT_TRUNCATED" and item["attempts"] == 1


def test_dedupe_key_uses_rendered_messages(api: Api, fast_model: dict[str, Any]) -> None:
    """03 第 4.7 节：模板里用了 {{row_number}} 时，两行原文相同也不会被合并。"""
    file = api.paste("同样的一句话\n同样的一句话")
    plain = api.ok(api.post("/api/jobs/estimate", api.job_body(file, model_id=fast_model["id"])))
    assert plain["duplicate_count"] == 1
    numbered = _prompt_copy(api, "classify", "带行号的识别", user_template="第 {{row_number}} 行：{{text}}")
    estimate = api.ok(api.post("/api/jobs/estimate", api.job_body(file, model_id=fast_model["id"],
                                                                  prompt_id=numbered["id"])))
    assert estimate["duplicate_count"] == 0 and estimate["request_count"] == 2
    job = api.create_job(file, model_id=fast_model["id"], prompt_id=numbered["id"])
    api.wait_job(job["id"])
    assert all(i["dedup_of"] is None and i["attempts"] == 1 for i in api.items(job["id"]))


def test_item_detail_render_meta_and_current_model(api: Api) -> None:
    """04 第 8 节 ItemDetail.messages：处理过的条目按 render_meta 重现当时发送的内容；还没处理过的条目按当前模型配置渲染。"""
    long_text = "很长的投诉内容" * 600
    done_model = api.mock_model("测试-截断字数", "fast", context_window=2048)
    job = api.create_job(api.paste(long_text), model_id=done_model["id"])
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    detail = api.ok(api.get(f"/api/jobs/{job['id']}/items/{item['id']}"))
    assert item["truncated"] and detail["omitted_chars"] and detail["omitted_chars"] > 0

    model = api.mock_model("测试-渲染参数", "auth", context_window=2048)
    file = api.paste("\n".join(f"第{i}条{long_text}" for i in range(3)))
    job = api.create_job(file, model_id=model["id"], concurrency=1, dedupe=False)
    api.wait_job(job["id"], ("paused",))
    first, second, _third = api.items(job["id"])   # 并发 1：只有第一条派发过（鉴权失败后回到 pending）
    first_before = api.ok(api.get(f"/api/jobs/{job['id']}/items/{first['id']}"))
    assert "中间省略" in first_before["messages"][-1]["content"]
    api.ok(api.patch(f"/api/models/{model['id']}", {"context_window": 32768}))
    first_after = api.ok(api.get(f"/api/jobs/{job['id']}/items/{first['id']}"))
    assert first_after["messages"] == first_before["messages"]
    second_after = api.ok(api.get(f"/api/jobs/{job['id']}/items/{second['id']}"))
    assert "中间省略" not in second_after["messages"][-1]["content"]
    assert second_after["messages"][-1]["content"].endswith(second_after["input_text"])
