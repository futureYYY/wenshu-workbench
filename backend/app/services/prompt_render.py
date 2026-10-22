"""变量渲染与消息组装（05 第 2 节），以及按输入预算规划请求（05 第 7 节）。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services import segmenter

VAR_RE = re.compile(r"\{\{\s*(col:[^{}]+?|[a-z_]+)\s*\}\}")

# “输入变量”：计算 overhead 时替换为空串；用户消息模板至少要引用其中之一（col: 也算）
INPUT_VARIABLES = frozenset({"text", "text_numbered", "row_json", "chunk_summaries"})
SAVE_REQUIRED_INPUTS = frozenset({"text", "text_numbered", "row_json"})

_COMMON = frozenset({"text", "row_number", "file_name", "row_json", "today", "col:"})
ALLOWED_BY_SLOT: dict[str, frozenset[str]] = {
    "system": _COMMON,
    "user": _COMMON | {"text_numbered"},
    "chunk": _COMMON | {"text_numbered", "chunk_index", "chunk_total"},
    "merge": _COMMON | {"chunk_summaries"},
}

# 05 第 2.2 节的变量清单（编辑器补全用）
VARIABLE_DEFS: list[dict[str, Any]] = [
    {
        "name": "text",
        "description": "本条文本。意图识别超长被截断时是截断后的文本；分段模板里是本段的原文",
        "templates": ["system", "user", "chunk", "merge"],
    },
    {
        "name": "text_numbered",
        "description": "切分并编号后的文本，每段一行，形如 [3] 段落内容；分段模板里只含本段的段落，编号是全文编号",
        "templates": ["user", "chunk"],
    },
    {"name": "row_number", "description": "原文件行号", "templates": ["system", "user", "chunk", "merge"]},
    {"name": "file_name", "description": "原文件名", "templates": ["system", "user", "chunk", "merge"]},
    {
        "name": "row_json",
        "description": "整行数据的 JSON，形如 {\"列标题\": \"值\"}",
        "templates": ["system", "user", "chunk", "merge"],
    },
    {
        "name": "col:",
        "description": "该行某一列的值，例如 {{col:客户等级}}；列不存在时为空字符串",
        "templates": ["system", "user", "chunk", "merge"],
    },
    {"name": "chunk_index", "description": "当前是第几段（仅分段模板）", "templates": ["chunk"]},
    {"name": "chunk_total", "description": "一共分了几段（仅分段模板）", "templates": ["chunk"]},
    {"name": "chunk_summaries", "description": "各段的摘要结果（仅合并模板）", "templates": ["merge"]},
    {"name": "today", "description": "当天日期，YYYY-MM-DD（本地时间）", "templates": ["system", "user", "chunk", "merge"]},
]

SUMMARIZE_ONLY_VARIABLES = frozenset({"chunk_index", "chunk_total", "chunk_summaries"})

# 随行变化的变量（file_name、today 在一个任务内不变）
ROW_VARYING_VARIABLES = frozenset({"text", "text_numbered", "row_number", "row_json"})


def local_today() -> str:
    """{{today}}：当天日期，YYYY-MM-DD（本地时间）。"""
    return datetime.now().strftime("%Y-%m-%d")


def variables_for(task_type: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for var in VARIABLE_DEFS:
        if task_type == "classify" and var["name"] in SUMMARIZE_ONLY_VARIABLES:
            continue
        templates = [t for t in var["templates"] if task_type == "summarize" or t in ("system", "user")]
        insert = "{{col:}}" if var["name"] == "col:" else "{{" + var["name"] + "}}"
        items.append({"name": var["name"], "insert": insert, "description": var["description"], "templates": templates})
    return items


# ---- 规格 ----


@dataclass
class PromptSpec:
    task_type: str
    system_prompt: str
    user_template: str
    chunk_template: str | None
    merge_template: str | None
    output_mode: str
    field_map: dict[str, Any]
    temperature: float | None
    max_output_tokens: int | None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> PromptSpec:
        return cls(
            task_type=str(data.get("task_type", "classify")),
            system_prompt=str(data.get("system_prompt") or ""),
            user_template=str(data.get("user_template") or ""),
            chunk_template=data.get("chunk_template"),
            merge_template=data.get("merge_template"),
            output_mode=str(data.get("output_mode") or "json"),
            field_map=dict(data.get("field_map") or {}),
            temperature=data.get("temperature"),
            max_output_tokens=data.get("max_output_tokens"),
        )


@dataclass
class RowContext:
    """一条数据在渲染时可用的信息。columns 为 (key, title)，按文件中的顺序。"""

    text: str
    row_number: int
    file_name: str
    row_values: dict[str, str] = field(default_factory=dict)
    columns: list[tuple[str, str]] = field(default_factory=list)
    today: str | None = None      # {{today}} 的值；None 表示当天（条目详情按 render_meta 里记录的日期重现）

    def column_value(self, name: str) -> str:
        name = name.strip()
        if name in self.row_values:
            return self.row_values[name]
        for key, title in self.columns:
            if title == name:
                return self.row_values.get(key, "")
        return ""

    def row_json(self) -> str:
        data: dict[str, str] = {}
        for key, title in self.columns:
            name = title if title and title not in data else key
            data[name] = self.row_values.get(key, "")
        if not self.columns:
            data = dict(self.row_values)
        return json.dumps(data, ensure_ascii=False)


@dataclass
class StageVars:
    text: str = ""
    text_numbered: str = ""
    chunk_index: int | None = None
    chunk_total: int | None = None
    chunk_summaries: str = ""


@dataclass
class Rendered:
    text: str
    unknown: list[str]


def render(template: str, row: RowContext, stage: StageVars, slot: str, *, blank_inputs: bool = False) -> Rendered:
    """已知变量替换为值（原样插入、只替换一遍）；未知变量原样保留并列出。"""
    allowed = ALLOWED_BY_SLOT[slot]
    unknown: list[str] = []
    today = row.today or local_today()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.startswith("col:"):
            if "col:" not in allowed:
                unknown.append(match.group(0))
                return match.group(0)
            return "" if blank_inputs else row.column_value(name[4:])
        if name not in allowed:
            unknown.append("{{" + name + "}}")
            return match.group(0)
        if blank_inputs and name in INPUT_VARIABLES:
            return ""
        if name == "text":
            return stage.text
        if name == "text_numbered":
            return stage.text_numbered
        if name == "row_number":
            return str(row.row_number)
        if name == "file_name":
            return row.file_name
        if name == "row_json":
            return row.row_json()
        if name == "chunk_index":
            return str(stage.chunk_index or "")
        if name == "chunk_total":
            return str(stage.chunk_total or "")
        if name == "chunk_summaries":
            return stage.chunk_summaries
        if name == "today":
            return today
        unknown.append("{{" + name + "}}")
        return match.group(0)

    text = VAR_RE.sub(replace, template or "")
    return Rendered(text, list(dict.fromkeys(unknown)))


def referenced_names(template: str | None) -> set[str]:
    names: set[str] = set()
    for match in VAR_RE.finditer(template or ""):
        name = match.group(1)
        names.add("col:" if name.startswith("col:") else name)
    return names


def has_required_input(user_template: str) -> bool:
    names = referenced_names(user_template)
    return bool(names & SAVE_REQUIRED_INPUTS) or "col:" in names


@dataclass
class Messages:
    messages: list[dict[str, str]]
    unknown: list[str]


def assemble(prompt: PromptSpec, template: str, row: RowContext, stage: StageVars, slot: str) -> Messages:
    """[system, user(模板)]；系统提示词渲染后为空时不发 system 消息。"""
    system = render(prompt.system_prompt, row, stage, "system")
    user = render(template, row, stage, slot)
    messages: list[dict[str, str]] = []
    if system.text.strip():
        messages.append({"role": "system", "content": system.text})
    messages.append({"role": "user", "content": user.text})
    return Messages(messages, list(dict.fromkeys(system.unknown + user.unknown)))


def overhead(prompt: PromptSpec, template: str, row: RowContext, slot: str, stage: StageVars | None = None) -> int:
    """overhead = estimate(系统提示词) + estimate(输入变量替换为空串后的模板) + 16 × 消息条数。"""
    stage = stage or StageVars(chunk_index=1, chunk_total=1)
    system = render(prompt.system_prompt, row, stage, "system", blank_inputs=True).text
    body = render(template, row, stage, slot, blank_inputs=True).text
    count = (1 if prompt.system_prompt.strip() else 0) + 1
    return segmenter.estimate_tokens(system) + segmenter.estimate_tokens(body) + 16 * count


def effective_max_output(prompt: PromptSpec, model_max_output: int) -> int:
    return int(prompt.max_output_tokens) if prompt.max_output_tokens is not None else int(model_max_output)


def effective_temperature(prompt: PromptSpec, model_temperature: float) -> float:
    return float(prompt.temperature) if prompt.temperature is not None else float(model_temperature)


class ContextTooSmall(Exception):
    """计算出的输入预算小于 256 tokens（05 第 6.1 节 CONTEXT_TOO_SMALL）。"""


def _budget(prompt: PromptSpec, template: str, row: RowContext, slot: str, context_window: int,
            max_output: int, factor: float) -> int:
    budget = segmenter.input_budget(context_window, max_output, overhead(prompt, template, row, slot), factor)
    if budget < segmenter.MIN_INPUT_BUDGET:
        raise ContextTooSmall(str(context_window))
    return budget


def main_budget(prompt: PromptSpec, row: RowContext, context_window: int, max_output: int, factor: float = 1.0) -> int:
    return _budget(prompt, prompt.user_template, row, "user", context_window, max_output, factor)


def input_tokens(prompt: PromptSpec, template: str, row: RowContext, stage: StageVars, slot: str) -> int:
    """模板里输入变量所占的 token 数（完整渲染减去输入变量置空后的渲染）。"""
    full = render(template, row, stage, slot).text
    blank = render(template, row, stage, slot, blank_inputs=True).text
    return max(0, segmenter.estimate_tokens(full) - segmenter.estimate_tokens(blank))


# ---- 请求规划 ----


@dataclass
class ClassifyPlan:
    messages: Messages
    truncated: bool
    omitted: int


def plan_classify(prompt: PromptSpec, row: RowContext, context_window: int, max_output: int,
                  factor: float = 1.0) -> ClassifyPlan:
    budget = main_budget(prompt, row, context_window, max_output, factor)
    cut = segmenter.truncate_middle(row.text, budget)
    stage = StageVars(text=cut.text)
    if "text_numbered" in referenced_names(prompt.user_template):
        stage.text_numbered = segmenter.numbered_text(segmenter.split_segments(cut.text))
    return ClassifyPlan(assemble(prompt, prompt.user_template, row, stage, "user"), cut.truncated, cut.omitted)


@dataclass
class SummarizePlan:
    segments: list[str]
    single: Messages | None                     # 不需要分段时的一次请求
    chunks: list[segmenter.Chunk] = field(default_factory=list)

    @property
    def chunk_count(self) -> int:
        return 1 if self.single is not None else len(self.chunks)


def summarize_main_stage(row: RowContext, segments: list[str]) -> StageVars:
    return StageVars(text=row.text, text_numbered=segmenter.numbered_text(segments))


def plan_summarize(prompt: PromptSpec, row: RowContext, context_window: int, max_output: int,
                   factor: float = 1.0) -> SummarizePlan:
    segments = segmenter.split_segments(row.text)
    stage = summarize_main_stage(row, segments)
    budget = main_budget(prompt, row, context_window, max_output, factor)
    if input_tokens(prompt, prompt.user_template, row, stage, "user") <= budget or len(segments) <= 0:
        return SummarizePlan(segments, assemble(prompt, prompt.user_template, row, stage, "user"))
    if not prompt.chunk_template or not prompt.merge_template:
        raise MissingTemplate("摘要模板缺少分段模板或合并模板")
    chunk_budget = _budget(prompt, prompt.chunk_template, row, "chunk", context_window, max_output, factor)
    chunks = segmenter.pack_chunks(segments, chunk_budget)
    if len(chunks) <= 1:
        # 按分段模板也只装得下一段：仍然按一次请求处理（模型会按上下文长度自行报错）
        return SummarizePlan(segments, assemble(prompt, prompt.user_template, row, stage, "user"))
    return SummarizePlan(segments, None, chunks)


class MissingTemplate(Exception):
    pass


def chunk_messages(prompt: PromptSpec, row: RowContext, chunk: segmenter.Chunk, index: int, total: int) -> Messages:
    stage = StageVars(text=chunk.text, text_numbered=chunk.numbered, chunk_index=index, chunk_total=total)
    return assemble(prompt, prompt.chunk_template or "", row, stage, "chunk")


def merge_budget(prompt: PromptSpec, row: RowContext, context_window: int, max_output: int, factor: float = 1.0) -> int:
    return _budget(prompt, prompt.merge_template or "", row, "merge", context_window, max_output, factor)


def merge_messages(prompt: PromptSpec, row: RowContext, parts: list[str]) -> Messages:
    stage = StageVars(text=row.text, chunk_summaries=segmenter.format_chunk_summaries(parts))
    return assemble(prompt, prompt.merge_template or "", row, stage, "merge")


def is_long_text(prompt: PromptSpec, row: RowContext, context_window: int, max_output: int) -> bool:
    """预估接口的 long_text_count：超出上下文、需要截断（识别）或分段（摘要）。"""
    budget = main_budget(prompt, row, context_window, max_output)
    if prompt.task_type == "classify":
        return segmenter.estimate_tokens(row.text) > budget
    stage = summarize_main_stage(row, segmenter.split_segments(row.text))
    return input_tokens(prompt, prompt.user_template, row, stage, "user") > budget


# ---- 去重键（03 第 4.7 节） ----


def normal_stage(prompt: PromptSpec, row: RowContext) -> StageVars:
    """“普通请求”的阶段变量：不截断、不分段。"""
    stage = StageVars(text=row.text)
    names = referenced_names(prompt.system_prompt) | referenced_names(prompt.user_template)
    if "text_numbered" in names:
        stage.text_numbered = segmenter.numbered_text(segmenter.split_segments(row.text))
    return stage


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class DedupeKeyer:
    """去重键：按任务的提示词快照把一行渲染成普通请求的完整消息（系统提示词 + 用户消息），序列化后取 sha1。

    只比较原文不够：模板里用了 {{row_number}}、{{col:…}}、{{row_json}} 时，两行原文相同、其他列不同，
    发给模型的内容并不相同。系统提示词不随行变化时只渲染一次（结果与逐行渲染完全相同）。
    """

    def __init__(self, prompt: PromptSpec, today: str | None = None) -> None:
        self.prompt = prompt
        self.today = today or local_today()
        names = referenced_names(prompt.system_prompt)
        self._system_varies = bool(names & ROW_VARYING_VARIABLES) or any(n.startswith("col:") for n in names)
        self._system_json: str | None = None

    def key(self, row: RowContext) -> str:
        row.today = row.today or self.today
        stage = normal_stage(self.prompt, row)
        if self._system_varies:
            payload = _compact_json(assemble(self.prompt, self.prompt.user_template, row, stage, "user").messages)
        else:
            if self._system_json is None:
                system = render(self.prompt.system_prompt, row, stage, "system").text
                self._system_json = _compact_json({"role": "system", "content": system}) if system.strip() else ""
            user = render(self.prompt.user_template, row, stage, "user").text
            user_json = _compact_json({"role": "user", "content": user})
            payload = f"[{self._system_json},{user_json}]" if self._system_json else f"[{user_json}]"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def dedupe_key(prompt: PromptSpec, row: RowContext) -> str:
    return DedupeKeyer(prompt, row.today).key(row)


# ---- 条目详情的重现（03 第 4.7 节 render_meta） ----


def budget_factor(prompt: PromptSpec, row: RowContext, context_window: int, max_output: int,
                  input_budget: int | None) -> float:
    """按 render_meta 里记录的输入预算反推当时用的缩小系数（上下文超长兜底每次 × 0.7，最多 2 次）。"""
    if input_budget is None:
        return 1.0
    factor = 1.0
    for _ in range(3):
        try:
            if main_budget(prompt, row, context_window, max_output, factor) <= input_budget:
                return factor
        except ContextTooSmall:
            return factor
        factor *= 0.7
    return factor
