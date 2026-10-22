"""内置提示词（05 第 3 节）与默认设置（03 第 5 节）。“恢复内置默认”使用这里的内容。"""

from __future__ import annotations

from typing import Any

CLASSIFY_BUILTIN_KEY = "classify.default"
SUMMARIZE_BUILTIN_KEY = "summarize.default"

CLASSIFY_SYSTEM_PROMPT = """你是一名严谨的意图识别助手。请判断用户文本表达的主要意图，并从下面的类别中选出最合适的一个。

## 意图类别
（使用前请把下面的示例类别换成你自己的类别，每行一个，格式为“- 类别名：说明”）
- 咨询：询问信息、规则、价格、流程等
- 办理：要求开通、变更、取消或退订某项业务
- 投诉：表达不满，要求处理或赔偿
- 建议：对产品或服务提出改进意见
- 其他：与以上类别都不相符，或文本没有实际含义

## 判断规则
1. 只选一个类别，必须是上面列出的类别名之一，原样输出，不要自创类别。
2. 文本包含多个意图时，选用户最想解决的那一个。
3. 文本过短、没有意义或无法判断时，选“其他”。
4. 只依据文本本身判断，不要猜测文本之外的信息。

## 输出格式
只输出一个 JSON 对象，不要输出任何其他内容：
{"intent": "类别名", "confidence": 0 到 1 之间的小数, "reason": "不超过 30 字的判断依据"}"""

CLASSIFY_USER_TEMPLATE = """请识别下面这段文本的意图：

{{text}}"""

SUMMARIZE_SYSTEM_PROMPT = """你是一名专业的摘要编辑。请为用户提供的文本写一份准确、精炼的中文摘要。

## 要求
1. 忠于原文：只写原文里有的信息，不添加、不评论、不推测。
2. 先用一到两句话概括全文主旨，再列出 3 到 6 条关键要点；原文很短时，要点可以少于 3 条。
3. 每条要点注明它来自原文的哪些段落，即原文每段开头方括号里的数字。
4. 主旨不超过 120 字，每条要点不超过 60 字。
5. 原文是外文时，摘要仍然用中文。

## 输出格式
只输出一个 JSON 对象，不要输出任何其他内容：
{"summary": "全文主旨", "key_points": [{"text": "要点", "sources": [段落编号]}]}"""

SUMMARIZE_USER_TEMPLATE = """原文如下，每段开头方括号里的数字是段落编号：

{{text_numbered}}"""

SUMMARIZE_CHUNK_TEMPLATE = """下面是一篇长文的第 {{chunk_index}} 部分，共 {{chunk_total}} 部分。每段开头方括号里的数字是全文的段落编号。请只为这一部分写摘要，要求和输出格式与前面的说明相同。

{{text_numbered}}"""

SUMMARIZE_MERGE_TEMPLATE = """下面是同一篇长文各部分的摘要，按顺序排列。请把它们合并成一份完整的摘要：重新概括全文主旨，合并重复的要点，保留每条要点的段落编号。要求和输出格式与前面的说明相同。

{{chunk_summaries}}"""

BUILTIN_PROMPTS: dict[str, dict[str, Any]] = {
    CLASSIFY_BUILTIN_KEY: {
        "task_type": "classify",
        "name": "默认意图识别",
        "description": "从提示词里列出的类别中选一个，输出类别、置信度和判断依据。使用前把示例类别换成自己的。",
        "system_prompt": CLASSIFY_SYSTEM_PROMPT,
        "user_template": CLASSIFY_USER_TEMPLATE,
        "chunk_template": None,
        "merge_template": None,
        "output_mode": "json",
        "field_map": {"label": "intent", "confidence": "confidence", "reason": "reason"},
        "temperature": 0.0,
        "max_output_tokens": 300,
    },
    SUMMARIZE_BUILTIN_KEY: {
        "task_type": "summarize",
        "name": "默认文本摘要",
        "description": "先概括主旨，再列 3 到 6 条要点，每条要点标出来自原文哪几段。",
        "system_prompt": SUMMARIZE_SYSTEM_PROMPT,
        "user_template": SUMMARIZE_USER_TEMPLATE,
        "chunk_template": SUMMARIZE_CHUNK_TEMPLATE,
        "merge_template": SUMMARIZE_MERGE_TEMPLATE,
        "output_mode": "json",
        "field_map": {"summary": "summary", "key_points": "key_points"},
        "temperature": 0.3,
        "max_output_tokens": 1500,
    },
}

BUILTIN_KEY_BY_TASK = {"classify": CLASSIFY_BUILTIN_KEY, "summarize": SUMMARIZE_BUILTIN_KEY}

# 提示词里会进入版本快照的“内容字段”（只改名称、说明时不产生新版本）
PROMPT_CONTENT_FIELDS = (
    "system_prompt",
    "user_template",
    "chunk_template",
    "merge_template",
    "output_mode",
    "field_map",
    "temperature",
    "max_output_tokens",
)

# 03 第 5 节的设置项；default_model_id.*、default_prompt_id.* 的默认值在初始化时按实际 id 填入
DEFAULT_SETTINGS: dict[str, Any] = {
    "default_concurrency.classify": 5,
    "default_concurrency.summarize": 5,
    "default_limit": 100,
    "default_max_retries": 2,
    "default_dedupe": True,
    "default_model_id.classify": None,
    "default_model_id.summarize": None,
    "default_prompt_id.classify": None,
    "default_prompt_id.summarize": None,
    "theme": "system",
    "open_mode": "app",
    "preferred_port": 18765,
    "show_demo_model": True,
    "first_close_hint_shown": False,
}

DEMO_MODEL_DEFAULTS: dict[str, Any] = {
    "name": "演示模型",
    "provider_kind": "demo",
    "base_url": "demo://local",
    "model": "wenshu-demo",
    "context_window": 32768,
    "notes": "不消耗额度，结果是模拟的",
}

PLACEHOLDER_MODEL_NOTES = "占位条目：编辑这个模型，填写真实的接口地址、API Key 和模型名，保存后会自动启用。"
