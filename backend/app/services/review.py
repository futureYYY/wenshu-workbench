"""人工复核（01 RES-06、RES-07、RES-11；04 第 8.2 节）：修正意图、修改摘要、标记已复核。

- 意图只能改成任务所用提示词（快照）里列出的类别（05 第 4.6 节）；改成与模型输出相同的类别视为撤销修正；
- 摘要只改主旨，要点保持模型输出；改成与模型输出相同的内容视为撤销修改；
- 只有处理成功的条目可以修正；撤销任何时候都可以；
- 修正（不含撤销）时自动标记已复核，请求里明确给了 reviewed 时以请求为准；
- manual_at 记最近一次人工修正的时间，没有修正时为 NULL。
"""

from __future__ import annotations

from typing import Any

from app.api.errors import conflict, field_error, unprocessable
from app.db.models import JobItemRow, JobRow
from app.schemas.jobs import ItemPatch
from app.services.output_parser import normalize_label, prompt_labels
from app.utils import loads, now_iso

NO_LABELS_MESSAGE = "这个任务的提示词没有按“- 类别名：说明”列出意图类别，不能人工修正"


def label_options(job: JobRow) -> list[str]:
    """意图识别任务的提示词快照里列出的类别；摘要任务为空列表。"""
    if job.task_type != "classify":
        return []
    snapshot = loads(job.prompt_snapshot_json, {}) or {}
    return prompt_labels(str(snapshot.get("system_prompt") or ""), str(snapshot.get("user_template") or ""))


def effective_summary(summary: str | None, manual_summary: str | None) -> str | None:
    """有效摘要（03 第 7 节）：人工修改过的取修改后的。"""
    return manual_summary if manual_summary is not None else summary


def effective_output_chars(output_chars: int | None, summary: str | None, manual_summary: str | None) -> int | None:
    """有效摘要加要点的字数：output_chars 是模型摘要加要点的字数，修改过时把摘要部分换成修改后的。"""
    if output_chars is None or manual_summary is None:
        return output_chars
    return max(0, int(output_chars) - len(summary or "") + len(manual_summary))


def _require_succeeded(item: JobItemRow) -> None:
    if item.status != "succeeded":
        raise conflict("JOB_STATE_CONFLICT", "只有处理成功的条目可以人工修正")


def patch_values(job: JobRow, item: JobItemRow, body: ItemPatch) -> dict[str, Any]:
    """校验 PATCH 请求，返回要写入的字段。"""
    provided = body.model_fields_set
    values: dict[str, Any] = {}
    touched = False
    if "manual_label" in provided:
        if job.task_type != "classify":
            raise field_error("manual_label", "只有意图识别任务可以修正意图")
        touched = True
        if body.manual_label is None:
            values["manual_label"] = None
        else:
            _require_succeeded(item)
            options = label_options(job)
            if not options:
                raise unprocessable("LABEL_NOT_IN_PROMPT", NO_LABELS_MESSAGE, labels=[])
            label = normalize_label(body.manual_label)
            if label not in options:
                raise unprocessable(
                    "LABEL_NOT_IN_PROMPT", f"只能改成提示词里列出的意图：{'、'.join(options)}", labels=options
                )
            values["manual_label"] = None if label == item.label else label
    if "manual_summary" in provided:
        if job.task_type != "summarize":
            raise field_error("manual_summary", "只有文本摘要任务可以修改摘要")
        touched = True
        if body.manual_summary is None:
            values["manual_summary"] = None
        else:
            _require_succeeded(item)
            text = body.manual_summary.strip()
            values["manual_summary"] = None if text == (item.summary or "").strip() else text
    if "reviewed" in provided and body.reviewed is not None:
        values["reviewed"] = body.reviewed
    if "note" in provided:
        values["note"] = body.note
    if touched:
        manual_label = values.get("manual_label", item.manual_label)
        manual_summary = values.get("manual_summary", item.manual_summary)
        values["manual_at"] = now_iso() if manual_label is not None or manual_summary is not None else None
        corrected_now = values.get("manual_label") is not None or values.get("manual_summary") is not None
        if corrected_now and "reviewed" not in values:
            values["reviewed"] = True
    return values
