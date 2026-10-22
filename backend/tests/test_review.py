"""人工复核（01 RES-06、RES-07、RES-11；04 第 8.2、9 节；05 第 4.6 节；08 第 10.1 节“人工复核”）。"""

from __future__ import annotations

import csv
import io
from typing import Any

from app.services.defaults import BUILTIN_PROMPTS
from app.services.output_parser import prompt_labels

from .conftest import Api, unique_lines

BUILTIN_LABELS = ["咨询", "办理", "投诉", "建议", "其他"]
SUMMARY_TEXT = "第一段讲了宽带掉线的问题，用户很着急。\n第二段说明工程师上门检查。\n第三段写了问题已经解决。"
NO_LABELS_PROMPT = {
    "task_type": "classify",
    "name": "没有列出类别",
    "system_prompt": "判断用户的情绪，只输出 JSON：{\"intent\": \"情绪\"}",
    "user_template": "{{text}}",
    "output_mode": "json",
    "field_map": {"label": "intent", "confidence": None, "reason": None},
}


def _item_url(job: dict[str, Any], item: dict[str, Any]) -> str:
    return f"/api/jobs/{job['id']}/items/{item['id']}"


def _csv_rows(api: Api, job_id: int) -> list[dict[str, str]]:
    resp = api.get(f"/api/jobs/{job_id}/export", params={"format": "csv"})
    assert resp.status_code == 200, resp.text
    rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    return [dict(zip(rows[0], row, strict=True)) for row in rows[1:]]


def _other_label(label: str | None) -> str:
    return next(name for name in BUILTIN_LABELS if name != label)


# ---- 提示词里列出的类别（05 第 4.6 节） ----


def test_prompt_labels_rules() -> None:
    builtin = BUILTIN_PROMPTS["classify.default"]
    assert prompt_labels(builtin["system_prompt"], builtin["user_template"]) == BUILTIN_LABELS
    # 规则 1：标题含“类别”的小节；数字列表、包裹符号、说明都能处理；分隔线和含变量的行不算；只取到下一个标题
    section = (
        "你是分类助手。\n### 可选类别\n1. 退款\n2、物流查询：问快递\n- 「投诉」：不满\n---\n- {{col:等级}}：变量\n"
        "## 规则\n- 注意：只输出 JSON\n"
    )
    assert prompt_labels(section, "{{text}}") == ["退款", "物流查询", "投诉"]
    # 规则 2：没有这样的小节时，取“- 类别名：说明”的行（与演示模型相同）
    assert prompt_labels("请分类。\n- 退款：要钱\n* 其他: 其他情况\n", "{{text}}") == ["退款", "其他"]
    # 类别写在用户消息模板里
    assert prompt_labels("你是助手", "## 意图类别\n- 甲：说明\n- 乙\n\n{{text}}") == ["甲", "乙"]
    assert prompt_labels("只判断情绪，输出 JSON", "{{text}}") == []


# ---- 修正意图 ----


def test_correct_intent(api: Api, fast_model: dict[str, Any]) -> None:
    job = api.create_job(api.paste(unique_lines("复核", 12)), model_id=fast_model["id"], limit=None)
    api.wait_job(job["id"])
    assert api.job(job["id"])["label_options"] == BUILTIN_LABELS
    item = api.items(job["id"], status="succeeded")[0]
    target = _other_label(item["label"])
    url = _item_url(job, item)

    patched = api.ok(api.patch(url, {"manual_label": target}))
    assert patched["manual_label"] == target and patched["effective_label"] == target
    assert patched["label"] == item["label"]                  # 修正前（模型的输出）保留
    assert patched["corrected"] and patched["reviewed"]       # 修正时自动标记已复核
    assert api.ok(api.get(url))["manual_at"]
    counts = {c["label"]: c["count"] for c in api.ok(api.get(f"/api/jobs/{job['id']}/categories"))["items"]}
    assert counts.get(target, 0) >= 1                         # 统计用修正后的类别
    assert [i["id"] for i in api.items(job["id"], corrected="true")] == [item["id"]]
    assert all(not i["corrected"] for i in api.items(job["id"], corrected="false"))

    # 先按 05 第 4.5 节规范化再比较
    assert api.ok(api.patch(url, {"manual_label": f"「{target}」。"}))["manual_label"] == target

    # 只能改成提示词里列出的类别
    err = api.error(api.patch(url, {"manual_label": "物流查询"}), 422, "LABEL_NOT_IN_PROMPT")
    assert err["detail"]["labels"] == BUILTIN_LABELS
    assert err["message"].startswith("只能改成提示词里列出的意图")
    # 意图识别任务不能改摘要
    api.error(api.patch(url, {"manual_summary": "一段摘要"}), 422, "VALIDATION_ERROR")

    # 改回模型的类别等于撤销修正，复核标记保留
    reverted = api.ok(api.patch(url, {"manual_label": item["label"]}))
    assert reverted["manual_label"] is None and not reverted["corrected"] and reverted["reviewed"]
    assert reverted["effective_label"] == item["label"]
    assert api.ok(api.get(url))["manual_at"] is None
    # null 撤销；reviewed 可以单独改
    api.ok(api.patch(url, {"manual_label": target}))
    cleared = api.ok(api.patch(url, {"manual_label": None, "reviewed": False}))
    assert cleared["manual_label"] is None and not cleared["reviewed"]
    assert api.items(job["id"], corrected="true") == []


def test_correct_requires_success_and_listed_labels(api: Api) -> None:
    bad = api.mock_model("复核-坏 JSON", "bad_json,fast")
    job = api.create_job(api.paste("复核失败甲"), model_id=bad["id"], dedupe=False)
    api.wait_job(job["id"])
    failed = api.items(job["id"], status="failed")[0]
    api.error(api.patch(_item_url(job, failed), {"manual_label": "咨询"}), 409, "JOB_STATE_CONFLICT")
    assert api.ok(api.patch(_item_url(job, failed), {"reviewed": True}))["reviewed"]   # 复核标记不限状态

    # 提示词没有列出类别：不能修正
    prompt = api.ok(api.post("/api/prompts", NO_LABELS_PROMPT), 201)
    fast = api.mock_model("复核-快速", "fast")
    plain = api.create_job(api.paste("没有类别甲"), model_id=fast["id"], prompt_id=prompt["id"])
    api.wait_job(plain["id"])
    assert api.job(plain["id"])["label_options"] == []
    item = api.items(plain["id"], status="succeeded")[0]
    err = api.error(api.patch(_item_url(plain, item), {"manual_label": item["label"]}), 422, "LABEL_NOT_IN_PROMPT")
    assert err["detail"]["labels"] == []


def test_rerun_keeps_manual_correction(api: Api, fast_model: dict[str, Any]) -> None:
    """单条重新处理只重置模型结果，人工修正和复核标记保留（04 第 8.2 节）。"""
    job = api.create_job(api.paste(unique_lines("重跑复核", 2)), model_id=fast_model["id"], dedupe=False)
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    target = _other_label(item["label"])
    api.ok(api.patch(_item_url(job, item), {"manual_label": target}))
    api.ok(api.post(f"{_item_url(job, item)}/rerun"))
    api.wait_job(job["id"])
    detail = api.ok(api.get(_item_url(job, item)))
    assert detail["status"] == "succeeded" and detail["label"]
    assert detail["manual_label"] == target and detail["effective_label"] == target and detail["reviewed"]


# ---- 修改摘要 ----


def test_edit_summary(api: Api, fast_model: dict[str, Any]) -> None:
    job = api.create_job(api.paste(SUMMARY_TEXT), task_type="summarize", model_id=fast_model["id"])
    api.wait_job(job["id"])
    assert api.job(job["id"])["label_options"] == []
    item = api.items(job["id"], status="succeeded")[0]
    url = _item_url(job, item)
    before = api.ok(api.get(url))
    edited = "人工改写：宽带掉线，工程师已上门修好。"

    patched = api.ok(api.patch(url, {"manual_summary": f"  {edited}  "}))
    assert patched["summary_preview"] == edited and patched["corrected"] and patched["reviewed"]
    key_point_chars = before["output_chars"] - len(before["summary"])
    assert patched["output_chars"] == len(edited) + key_point_chars          # 字数、压缩比按修改后的摘要
    assert patched["compression_ratio"] == round(before["input_chars"] / patched["output_chars"], 1)
    after = api.ok(api.get(url))
    assert after["summary"] == before["summary"] and after["manual_summary"] == edited   # 修改前后都能看到
    assert after["key_points"] == before["key_points"] and after["manual_at"]
    succeeded = api.items(job["id"], status="succeeded")
    compression = api.job(job["id"])["compression"]
    assert compression["output_chars"] == sum(i["output_chars"] for i in succeeded)
    assert [i["id"] for i in api.items(job["id"], q="人工改写")] == [item["id"]]

    api.error(api.patch(url, {"manual_label": "咨询"}), 422, "VALIDATION_ERROR")
    api.error(api.patch(url, {"manual_summary": "   "}), 422, "VALIDATION_ERROR")

    reverted = api.ok(api.patch(url, {"manual_summary": None}))
    assert reverted["summary_preview"] == before["summary_preview"] and not reverted["corrected"]
    assert reverted["output_chars"] == before["output_chars"]
    same = api.ok(api.patch(url, {"manual_summary": before["summary"]}))   # 与模型输出相同等于撤销
    assert not same["corrected"] and api.ok(api.get(url))["manual_summary"] is None


# ---- 导出（04 第 9 节） ----


def test_export_before_and_after(api: Api, fast_model: dict[str, Any]) -> None:
    job = api.create_job(api.paste(unique_lines("导出复核", 3)), model_id=fast_model["id"])
    api.wait_job(job["id"])
    item = api.items(job["id"])[0]
    target = _other_label(item["label"])
    api.ok(api.patch(_item_url(job, item), {"manual_label": target}))
    rows = _csv_rows(api, job["id"])
    assert rows[0]["意图"] == target and rows[0]["修正前意图"] == item["label"]
    assert rows[0]["人工修正"] == "是" and rows[0]["已复核"] == "是"
    assert all(r["修正前意图"] == "" and r["人工修正"] == "" for r in rows[1:])

    summary_job = api.create_job(api.paste(SUMMARY_TEXT), task_type="summarize", model_id=fast_model["id"])
    api.wait_job(summary_job["id"])
    first = api.items(summary_job["id"])[0]
    model_summary = api.ok(api.get(_item_url(summary_job, first)))["summary"]
    edited = "人工改写的摘要。"
    patched = api.ok(api.patch(_item_url(summary_job, first), {"manual_summary": edited}))
    rows = _csv_rows(api, summary_job["id"])
    assert rows[0]["摘要"] == edited and rows[0]["修正前摘要"] == model_summary
    assert rows[0]["人工修正"] == "是" and rows[0]["已复核"] == "是"
    assert int(rows[0]["摘要字数"]) == patched["output_chars"]
    assert all(r["修正前摘要"] == "" and r["人工修正"] == "" for r in rows[1:])
