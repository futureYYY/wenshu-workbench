# 05 提示词与模型调用

> 文枢开发文档 · 第 5 篇。本文规定怎样把一条数据变成一次模型请求，以及怎样把模型输出变成结构化结果。实现集中在 `backend/app/services/` 的 `llm_client.py`、`prompt_render.py`、`output_parser.py`、`segmenter.py`、`defaults.py`，以及 `backend/app/api/mock.py`。

## 1. 调用约定

### 1.1 请求构造

只调用 Chat Completions：`POST {base_url}/chat/completions`。使用官方 `openai` Python SDK（3.x）的 `AsyncOpenAI`，SDK 自带的重试关闭，重试由任务引擎负责（第 6 节）。

openai 3.x 的底层 HTTP 客户端是 `httpx2`（httpx 的后续版本，`verify`、`proxy`、`limits` 等参数与 httpx 0.28 同名），SDK 提供 `DefaultAsyncHttpx2Client`，在 httpx2 客户端上保留了 SDK 的默认设置。若安装版本的类名或参数与下面不一致，以 SDK 仓库里的 httpx2 迁移说明为准。

```python
import httpx2
from openai import AsyncOpenAI, DefaultAsyncHttpx2Client

client = AsyncOpenAI(
    base_url=resolved_base_url,          # 演示模型解析为 http://127.0.0.1:{当前端口}/mock/v1
    api_key=api_key or "EMPTY",          # 本机 Ollama、vLLM 可以不填密钥
    timeout=float(cfg.timeout_s),
    max_retries=0,
    default_headers=cfg.extra_headers,
    http_client=DefaultAsyncHttpx2Client(
        verify=cfg.verify_ssl,
        proxy=cfg.proxy_url or None,     # 只用模型配置里填的代理
        trust_env=False,                 # 不读环境变量和系统代理，见下方“代理”
        limits=httpx2.Limits(max_connections=cfg.concurrency_cap,
                             max_keepalive_connections=cfg.concurrency_cap),
    ),
)

params = {
    "model": cfg.model,
    "messages": messages,
    "temperature": effective_temperature,
    cfg.max_tokens_param: effective_max_output_tokens,   # max_tokens 或 max_completion_tokens
}
if cfg.json_mode and prompt.output_mode == "json":
    params["response_format"] = {"type": "json_object"}

extra_body = {}
for key, value in cfg.extra_body.items():
    if key in ("model", "messages", "stream"):
        continue                          # 不允许覆盖，记一条警告日志
    if value is None:
        params.pop(key, None)             # 值为 null 表示“不发送这个参数”，例如 {"temperature": null}
    else:
        extra_body[key] = value

resp = await client.chat.completions.create(**params, extra_body=extra_body or None)
```

- **代理**：一律 `trust_env=False`，代理只认模型配置里的 `proxy_url`，留空就是直连。HTTP 客户端默认 `trust_env=True`，会读 `HTTPS_PROXY` 等环境变量，在 Windows 上还会读注册表里的系统代理；开着 Clash 之类的代理软件时，发往本机演示模型、本机 Ollama、公司内网网关的请求都会被送进代理而失败。需要代理的模型（例如访问海外接口）在配置里明确填写代理地址，只支持 `http://` 和 `https://` 代理。
- **证书**：openai 3.x 默认使用 Windows 系统证书库。公司内网网关的根证书如果已经装进系统，不需要关闭证书校验；`verify_ssl = false` 只作为最后手段。
- **有效温度**：提示词模板的 `temperature` 非空时用它，否则用模型配置的 `temperature`。
- **有效最大输出**：提示词模板的 `max_output_tokens` 非空时用它，否则用模型配置的。
- **JSON 模式**：OpenAI 要求消息里出现“JSON”字样，内置提示词已满足。很多兼容接口不支持该参数，所以默认关闭，由用户在模型配置里打开。
- **用量**：取 `resp.usage.prompt_tokens`、`completion_tokens`；上游没返回时用第 7.1 节的估算值。
- **非标准字段**：思考内容可能在 `message.reasoning_content` 或 `message.reasoning`，从 `message.model_extra`（或 `getattr`）读取，见第 5 节。

### 1.2 地址规范化

保存模型配置和发起请求前，对用户填写的地址做同样处理：

1. 去掉首尾空白；
2. 去掉末尾的 `/`；
3. 若以 `/chat/completions` 结尾则去掉，再去掉末尾的 `/`；
4. 必须以 `http://` 或 `https://` 开头，否则校验失败。

不自动补 `/v1`，因为有的网关不用它。测试连接返回 404 且地址里没有 `/v1` 时，在结论后提示“地址可能少了 /v1”。实际请求地址 `request_url = base_url + "/chat/completions"`。

### 1.3 客户端缓存

每个模型配置缓存一个 `AsyncOpenAI` 实例，缓存键为 `(id, updated_at)`；配置修改后下次取用时重建，旧实例在没有进行中的请求后关闭。程序退出时全部关闭。`updated_at` 只在用户新建、修改配置时更新，写入测试结果和平均耗时不改它（03 第 3 节），否则客户端会被频繁重建。

### 1.4 流式

只有试运行使用流式（`stream=True`）。逐块读取 `delta.content`，思考增量从 `delta.reasoning_content` 或 `delta.reasoning` 读取。不发送 `stream_options`（不少兼容接口不认），流式结束后若拿不到用量就用估算值。

## 2. 提示词模板

### 2.1 组成

| 字段 | 意图识别 | 文本摘要 | 说明 |
|---|---|---|---|
| `system_prompt` | 必填 | 必填 | 渲染后作为 system 消息；内容为空时不发 system 消息 |
| `user_template` | 必填 | 必填 | 渲染后作为 user 消息 |
| `chunk_template` | 不用 | 必填 | 长文本分段时，每一段的 user 消息 |
| `merge_template` | 不用 | 必填 | 合并各段摘要时的 user 消息 |
| `output_mode` | json / text | json / text | 输出怎么解析 |
| `field_map` | label、confidence、reason | summary、key_points | JSON 模式下各结果取哪个字段 |
| `temperature`、`max_output_tokens` | 可空 | 可空 | 覆盖模型配置的默认值 |

### 2.2 变量

| 变量 | 可用于 | 说明 |
|---|---|---|
| `{{text}}` | 全部模板 | 本条文本。意图识别超长被截断时是截断后的文本；分段模板里是本段的原文 |
| `{{text_numbered}}` | 用户、分段 | 切分并编号后的文本，每段一行，形如 `[3] 段落内容`（规则见第 7.2 节）。分段模板里只含本段的段落，但编号是全文编号 |
| `{{row_number}}` | 全部 | 原文件行号 |
| `{{file_name}}` | 全部 | 原文件名 |
| `{{row_json}}` | 全部 | 整行数据的 JSON，`{"列标题": "值"}` |
| `{{col:列标题}}` | 全部 | 该行某一列的值，例如 `{{col:客户等级}}`；列不存在时为空字符串 |
| `{{chunk_index}}`、`{{chunk_total}}` | 分段 | 当前是第几段、共几段 |
| `{{chunk_summaries}}` | 合并 | 各段的摘要结果，格式见第 7.4 节 |
| `{{today}}` | 全部 | 当天日期，`YYYY-MM-DD`（本地时间） |

### 2.3 渲染规则

- 匹配：`\{\{\s*(col:[^{}]+?|[a-z_]+)\s*\}\}`；
- 已知变量替换为值，原样插入，不做转义；
- 未知变量原样保留，并在渲染结果的 `unknown_variables` 里列出；
- 只替换一遍，值里即使含有 `{{…}}` 也不会再次替换；
- 系统提示词也会渲染（可以在里面用 `{{today}}` 等变量）。

### 2.4 消息组装

| 阶段 | 消息 |
|---|---|
| 普通请求（意图识别；摘要不分段） | `[system, user(user_template)]` |
| 摘要分段 | `[system, user(chunk_template)]` |
| 摘要合并 | `[system, user(merge_template)]` |
| 解析失败后的纠正请求 | 原消息 + `assistant(上次原始输出)` + `user(纠正说明)`，见第 4.4 节 |

## 3. 内置提示词

出厂内容写在 `backend/app/services/defaults.py`，“恢复内置默认”使用这里的内容。

### 3.1 意图识别（`builtin_key = classify.default`）

- 名称：默认意图识别
- 说明：从提示词里列出的类别中选一个，输出类别、置信度和判断依据。使用前把示例类别换成自己的。人工修正时只能改成这里列出的类别（第 4.6 节）。
- `output_mode`：`json`
- `field_map`：`{"label": "intent", "confidence": "confidence", "reason": "reason"}`
- `temperature`：`0`
- `max_output_tokens`：`300`

系统提示词：

```text
你是一名严谨的意图识别助手。请判断用户文本表达的主要意图，并从下面的类别中选出最合适的一个。

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
{"intent": "类别名", "confidence": 0 到 1 之间的小数, "reason": "不超过 30 字的判断依据"}
```

用户消息模板：

```text
请识别下面这段文本的意图：

{{text}}
```

### 3.2 文本摘要（`builtin_key = summarize.default`）

- 名称：默认文本摘要
- 说明：先概括主旨，再列 3 到 6 条要点，每条要点标出来自原文哪几段。
- `output_mode`：`json`
- `field_map`：`{"summary": "summary", "key_points": "key_points"}`
- `temperature`：`0.3`
- `max_output_tokens`：`1500`

系统提示词：

```text
你是一名专业的摘要编辑。请为用户提供的文本写一份准确、精炼的中文摘要。

## 要求
1. 忠于原文：只写原文里有的信息，不添加、不评论、不推测。
2. 先用一到两句话概括全文主旨，再列出 3 到 6 条关键要点；原文很短时，要点可以少于 3 条。
3. 每条要点注明它来自原文的哪些段落，即原文每段开头方括号里的数字。
4. 主旨不超过 120 字，每条要点不超过 60 字。
5. 原文是外文时，摘要仍然用中文。

## 输出格式
只输出一个 JSON 对象，不要输出任何其他内容：
{"summary": "全文主旨", "key_points": [{"text": "要点", "sources": [段落编号]}]}
```

用户消息模板：

```text
原文如下，每段开头方括号里的数字是段落编号：

{{text_numbered}}
```

分段模板：

```text
下面是一篇长文的第 {{chunk_index}} 部分，共 {{chunk_total}} 部分。每段开头方括号里的数字是全文的段落编号。请只为这一部分写摘要，要求和输出格式与前面的说明相同。

{{text_numbered}}
```

合并模板：

```text
下面是同一篇长文各部分的摘要，按顺序排列。请把它们合并成一份完整的摘要：重新概括全文主旨，合并重复的要点，保留每条要点的段落编号。要求和输出格式与前面的说明相同。

{{chunk_summaries}}
```

## 4. 输出解析

### 4.1 预处理（两种模式共用）

1. 取 `content`（为 `None` 时当作空字符串）；
2. 按第 5 节剥离思考内容；
3. 去掉首尾空白；
4. 去掉代码围栏：整段被 ```` ```json ```` 或 ```` ``` ```` 包裹时取里面的内容。

### 4.2 JSON 模式

**提取 JSON 对象**，按顺序尝试：

1. 整段直接 `json.loads`；
2. 从第一个 `{` 开始，按括号配对（跳过字符串里的括号）截出第一个完整对象，再 `json.loads`；
3. 用 `json_repair` 修复第 2 步截出的片段（截不出时修复整段）后解析；
4. 解析结果是只含一个对象的数组时，取这个对象；
5. 仍然得不到对象：解析失败，原因“输出不是 JSON”。

**意图识别**，按 `field_map` 取值：

| 结果 | 规则 |
|---|---|
| `label` | 必需。转成字符串后规范化（第 4.5 节）；缺失或为空时解析失败，原因“缺少 intent 字段”（写实际的字段名） |
| `confidence` | 可选。接受数字或数字字符串；`"85%"` 视为 0.85；大于 1 且不超过 100 时除以 100；最后限制在 0 到 1 之间；无法识别时为 `null` |
| `reason` | 可选。转成字符串，去掉首尾空白，最长 500 字 |

**文本摘要**：

| 结果 | 规则 |
|---|---|
| `summary` | 必需。非空字符串；缺失或为空时解析失败 |
| `key_points` | 可选。必须是数组，每个元素可以是：对象（文字取 `text`、`point` 或 `content` 字段，来源取 `sources` 或 `source`，可以是整数、数字字符串或它们的数组）；或字符串（来源为空）。丢弃文字为空的元素；来源只保留 1 到段落总数之间的整数，去重并排序 |
| `output_chars` | `summary` 的字数加全部要点文字的字数 |

`result_json` 保存提取出的完整对象（不只是映射的字段）。

### 4.3 纯文本模式

- 意图识别：取第一个非空行，去掉开头的“意图：”“类别：”“分类：”“intent:”“label:”（不区分大小写，中英文冒号均可），再按第 4.5 节规范化。`confidence`、`reason` 为 `null`。
- 文本摘要：整段内容作为 `summary`，`key_points` 为空数组。
- `result_json` 为 `{"text": 内容}`。

### 4.4 解析失败的纠正请求

非截断原因导致的解析失败，发一次纠正请求：原消息后追加 `assistant` 消息（上次的原始输出）和 `user` 消息：

```text
你上一次的输出无法解析：{失败原因}。请只输出一个符合要求的 JSON 对象，不要输出任何其他文字。
```

纠正请求计入 `attempts`，但不占网络重试次数。仍然失败时条目失败，`error_code = PARSE_ERROR`，原始输出保留，方便用户据此修改提示词。纯文本模式不会解析失败（意图识别输出为空时按 `EMPTY_OUTPUT` 处理）。

### 4.5 类别规范化

1. 转为字符串，去掉首尾空白，内部连续空白合并为一个空格；
2. 去掉成对包裹的符号：`「」` `『』` `“”` `""` `''` `‘’` `【】` `[]` `()` `（）` `《》` `<>`；
3. 去掉末尾的 `。` `．` `.` `，` `,` `；` `;` `：` `:` `！` `!` `？` `?`；
4. 超过 64 字时截到 64 字；
5. 结果为空视为解析失败，原因“类别为空”。

不做同义词归并，归并由用户在结果页手动完成（RES-08，P1）。

### 4.6 提示词里列出的类别

人工修正意图（01 RES-06）只能改成任务所用提示词里列出的类别。类别从任务的提示词快照里取，结果放在 `Job.label_options`（04 第 8 节），实现见 `output_parser.prompt_labels`：

1. 依次看系统提示词、用户消息模板。找标题行（`#` 到 `######`）文字里含“类别”的那一节（例如内置提示词的 `## 意图类别`），到下一个标题行为止；节里的每个列表项（`- `、`* `、`+ `，或 `1.`、`1、`、`1)`）是一个类别；
2. 都没有这样的小节时，取形如 `- 类别名：说明` 的行，正则与演示模型相同（第 8.2 节）：`^\s*[-*]\s*([^：:\s]{1,20})\s*[：:]`；
3. 类别名是列表项里第一个中文或英文冒号之前的文字，按第 4.5 节规范化；含模板变量（`{{`）、或不含文字（例如分隔线 `---`）的不算；去重，保持出现顺序，最多 200 个；
4. 一个都取不到时 `label_options` 为空数组，这个任务的意图不能人工修正，界面说明“这个任务的提示词没有按‘- 类别名：说明’列出意图类别，不能人工修正”。

内置提示词列出的类别是 `咨询、办理、投诉、建议、其他`。用户改提示词时，保持“每行一个，格式为‘- 类别名：说明’”，修正时就能选到这些类别。

## 5. 思考模型

思考内容可能出现在三个地方，全部收集到条目的 `reasoning` 字段（最长保留 20,000 字），不参与解析：

1. `message.reasoning_content`；
2. `message.reasoning`；
3. `content` 里的 `<think>…</think>` 块：全部取出后从 `content` 中删除。只有结束标签 `</think>`、没有开始标签时，最后一个 `</think>` 之前的内容都算思考。

思考过程会消耗输出 tokens。若输出因达到上限而截断（`finish_reason = "length"`）且有思考内容，错误说明里加一句建议：“这个模型会先思考再回答，请调大最大输出，或在额外请求体里关闭思考”。关闭思考的参数因模型而异（例如有的接口用 `{"enable_thinking": false}`，vLLM 部署的模型常用 `{"chat_template_kwargs": {"enable_thinking": false}}`），以各家文档为准。

## 6. 错误分类与重试

### 6.1 错误码

| error_code | 判定 | 重试 | 结果 | 中文说明（`error_message`） |
|---|---|---|---|---|
| `TIMEOUT` | `APITimeoutError`，或底层 HTTP 客户端的超时异常 | 是 | 重试用尽后条目失败 | 请求超时（{timeout_s} 秒） |
| `CONNECTION_ERROR` | `APIConnectionError`（非超时） | 是 | 同上 | 连不上 {host}：{原因} |
| `RATE_LIMITED` | HTTP 429 | 是，优先按 `Retry-After` 等待 | 同上 | 被限流（HTTP 429），{n} 秒后重试 |
| `SERVER_ERROR` | HTTP 500–599 | 是 | 同上 | 模型服务出错（HTTP {status}） |
| `EMPTY_OUTPUT` | `content` 为空且没有思考内容 | 是 | 同上 | 模型返回了空内容 |
| `AUTH_FAILED` | HTTP 401、403 | 否 | 条目回到 pending，任务暂停 | 密钥无效或无权限（HTTP {status}） |
| `MODEL_NOT_FOUND` | HTTP 404 | 否 | 条目回到 pending，任务暂停 | 模型“{model}”不存在，或接口地址不对（HTTP 404） |
| `CONTEXT_TOO_LONG` | HTTP 400 或 413，错误信息含 `context_length`、`maximum context`、`context window`、`context length`、`prompt is too long`、`input is too long`、`超出上下文`、`上下文长度` 之一（不区分大小写），且不含 `max_tokens`、`max_completion_tokens`（那是最大输出参数超限，按 `BAD_REQUEST` 处理） | 缩小预算后重试，最多 2 次（第 7.5 节） | 用尽后条目失败 | 文本超出模型的上下文长度 |
| `CONTEXT_TOO_SMALL` | 计算出的输入预算小于 256 tokens | 否 | 条目失败 | 模型上下文长度设置过小（{context_window}），放不下提示词和输出 |
| `BAD_REQUEST` | 其他 400、422 | 否 | 条目失败 | 请求被拒绝（HTTP {status}）：{上游错误信息的前 200 字} |
| `PARSE_ERROR` | 输出无法按第 4 节解析 | 纠正请求 1 次 | 条目失败，保留原始输出 | 输出无法解析：{原因} |
| `OUTPUT_TRUNCATED` | `finish_reason = "length"` 且 JSON 解析失败 | 有效最大输出小于 8192 时，翻倍（不超过 8192）重试 1 次；已经 ≥ 8192 时不重试 | 条目失败 | 输出被截断，请调大最大输出 tokens |
| `INTERNAL_ERROR` | 其他异常 | 否 | 条目失败，日志记录堆栈 | 内部错误：{异常类名} |

纯文本模式下 `finish_reason = "length"` 不算失败，结果照常保存，并在尝试记录里写“输出达到最大长度，可能不完整”。

### 6.2 重试节奏

- 可重试错误最多重试 `jobs.max_retries` 次（默认 2，即最多请求 3 次）；
- 第 n 次重试前等待 `min(30, 2^(n−1)) + random(0, 0.5)` 秒，即约 1、2、4…秒；
- 响应带 `Retry-After`（秒数或 HTTP 日期）时改为等待该时长，最长 60 秒；
- 等待期间释放模型级并发名额，但保留任务级名额；并行轨道显示“限流，3 秒后重试”或“第 2 次重试”，`Track.phase = waiting_retry`；
- 每次请求（含失败）追加一条尝试记录（03 第 4.5 节）。

### 6.3 任务级处理

- **鉴权失败、模型不存在**：触发的条目回到 pending（不算失败），任务立即暂停，`status_reason_code` 为 `auth_failed` 或 `model_not_found`，`status_reason` 写对应文案（03 第 6.1 节），进行中的其他条目结束后不再派发。
- **熔断**：连续 10 条条目以 `TIMEOUT`、`CONNECTION_ERROR`、`SERVER_ERROR` 最终失败时任务暂停，`status_reason_code = circuit_breaker`；任意一条成功即清零计数。触发熔断的这些条目保持 failed（它们确实失败了），用户修好网络或模型后点“继续”处理剩下的，再点“重试失败项”补做这些。
- **取消与暂停打断**：被中断的请求不计入失败，条目回到 pending。

### 6.4 平均耗时

每次成功的普通请求（不含分段、合并）完成后，更新模型配置的 `avg_latency_ms`：`新值 = 旧值 × 0.8 + 本次 × 0.2`（旧值为空时直接取本次）。随批量写入一起提交。

## 7. 长文本

### 7.1 token 估算与输入预算

不依赖分词器（`tiktoken` 首次使用要联网下载词表，离线环境会失败）。估算公式：

```python
CJK = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")

def estimate_tokens(s: str) -> int:
    cjk = len(CJK.findall(s))
    return math.ceil(cjk * 1.0 + (len(s) - cjk) / 3.5)
```

每个阶段的输入预算：

```
overhead     = estimate(渲染后的系统提示词) + estimate(把输入变量都替换为空串后的用户模板) + 16 × 消息条数
input_budget = floor((context_window − 有效最大输出 − overhead) × 0.9)
```

`input_budget < 256` 时条目失败，`error_code = CONTEXT_TOO_SMALL`。预估接口（04 第 8 节）用同样的算法统计 `long_text_count`。

### 7.2 段落切分与编号（摘要）

切分必须是确定性的纯函数：条目详情接口会用同一个函数重新切分，得到与模型看到的完全相同的段落编号。

1. 换行统一为 `\n`，按 `\n` 切开，去掉每段首尾空白，丢弃空段；
2. 超过 600 字的段落，在句末标点（`。！？!?；;`）后切开，再把相邻句子合并成不超过 400 字的小段；单句超过 400 字时每 400 字硬切一次；
3. 依次编号 1 到 n；
4. `text_numbered` 为每段一行，格式 `[编号] 段落内容`，行与行之间用一个换行分隔。

### 7.3 意图识别的截断

```python
if estimate_tokens(text) <= input_budget:
    use text
else:
    chars_per_token = len(text) / estimate_tokens(text)
    keep = floor(input_budget * chars_per_token) - 20
    head = text[: floor(keep * 0.7)]
    tail = text[len(text) - floor(keep * 0.3):]
    omitted = len(text) - len(head) - len(tail)
    text = f"{head}\n……（中间省略 {omitted} 字）……\n{tail}"
    truncated = True
```

截断时把 `omitted` 写入条目的 `omitted_chars`，并把当时的输入预算写入 `render_meta_json`（03 第 4.7 节），条目详情据此重现发送内容。

### 7.4 摘要的分段与合并

1. 全文编号后的文本不超过普通请求的输入预算：一次请求完成，`chunk_count = 1`；
2. 否则按分段模板计算预算，把**连续的**段落依次装进分段，每段不超过预算；单个段落本身超出预算时，按字数硬切成几块，每块沿用同一个编号；
3. 依次请求每一段（P0 在同一个并发名额里顺序执行；P1 允许单条内最多 3 段并行，仍受模型级并发上限约束），每段的输出按第 4 节解析，失败按第 6 节重试；任一段最终失败则整条失败；
4. 合并：`{{chunk_summaries}}` 由各段结果拼成：

```text
第 1 部分：
{"summary": "…", "key_points": [{"text": "…", "sources": [1, 2]}]}

第 2 部分：
{"summary": "…", "key_points": […]}
```

JSON 模式下每部分是该段解析出的对象（`ensure_ascii=False`）；纯文本模式下是该段的文字；

5. 合并内容超出合并模板的预算时，把相邻的部分分组，每组先合并一次，得到新的部分列表，重复直到只剩一份；
6. 最终结果取最后一次合并的解析结果。`chunk_count` 为分段数；tokens、耗时为所有请求之和；尝试记录的 `phase` 写 `chunk i/n` 或 `merge`。

### 7.5 上下文超长的兜底

上游返回 `CONTEXT_TOO_LONG` 时（说明模型配置里的上下文长度填大了），把该条目的输入预算乘以 0.7，重新截断（意图识别）或分段（摘要）后再请求，最多 2 次，仍失败则条目失败。

## 8. 演示模型

挂在 `/mock/v1`，接口形态见 04 第 11 节。目的：不用密钥、不联网就能完整体验和测试全部流程。正式版也保留。

### 8.1 判断请求类型

| 条件 | 类型 |
|---|---|
| system 消息含 `"intent"` | 意图识别 |
| system 消息含 `"summary"` | 文本摘要。最后一条 user 消息里有一行恰好是“第 1 部分：”（正则 `(?m)^第 1 部分：$`，即第 7.4 节合并格式的开头）时为合并请求，否则为普通或分段请求。不要用“包含‘第 1 部分’”判断：分段模板第 1 段的开头“下面是一篇长文的第 1 部分，共 N 部分”也包含这几个字 |
| 其他 | 回显：返回 `OK`（测试连接用） |

演示模型只按内置字段名（`intent`、`confidence`、`reason`、`summary`、`key_points`）输出 JSON，用户改了输出字段名后演示模型不会跟着变。

### 8.2 意图识别

1. 从 system 消息里提取类别：匹配 `^\s*[-*]\s*([^：:\s]{1,20})\s*[：:]` 的行，取类别名；一个都没有时用 `咨询、办理、投诉、建议、其他`；
2. 最后一条 user 消息里出现了某个类别名，就选它；否则按 `sha1(user 消息)` 取模选一个（同样的文本总是得到同样的类别）；
3. `confidence = 0.55 + (哈希值 % 44) / 100`；`reason = "演示模型：根据文本关键词判断"`；
4. 输出 `{"intent": 类别, "confidence": 置信度, "reason": 依据}`。

### 8.3 文本摘要

- 普通请求和分段请求：从 user 消息里取 `[n] 内容` 形式的行（取不到就按行切）；`summary` 为“演示摘要：”加第 1 段的第一句（最多 80 字）；`key_points` 最多 3 条，分别取第 1 段、中间一段、最后一段的第一个分句（最多 40 字），`sources` 为对应编号；
- 合并请求：`summary` 为“演示摘要：合并了 N 部分”，`key_points` 取各部分要点的前 4 条。

### 8.4 延迟、流式与用量

- 意图识别类随机 300–1200 毫秒，摘要类随机 800–2500 毫秒；
- `stream = true` 时按 SSE 分块返回，每块 1–4 个字，间隔 15–40 毫秒，最后一块带 `finish_reason`，以 `data: [DONE]` 结束；
- `usage` 按第 7.1 节估算。

### 8.5 故障模拟

- 环境变量 `WENSHU_MOCK_FAIL_RATE`（默认 `0.02`）：按此概率随机返回故障，一半是 429（带 `Retry-After: 1`），一半是 500。随机故障**只注入到非流式的意图识别和摘要请求**（任务引擎发的请求）；流式请求（试运行）和回显请求（测试连接）从不注入，因为它们不重试，注入只会让试运行、测试连接和自检无故失败。自动化测试和自检里设为 `0`。
- “首次请求”类行为（`rate_limit_first`、`server_error_first`）按“请求里的 `model` + 全部消息内容的 sha1”记录是否见过，记录在演示模型进程内，`POST /mock/v1/_reset` 清空（04 第 11 节）。测试前先重置，否则之前请求过同样内容就不会再出现首次故障。
- 演示模型统计正在处理的请求数和最大值，供并发相关的验收使用（`GET /mock/v1/_stats`）。
- 请求头 `X-Mock-Behavior`（逗号分隔多个，可通过模型配置的“自定义请求头”设置）：

| 值 | 效果 |
|---|---|
| `none` | 关闭随机故障 |
| `rate_limit` | 总是返回 429，`Retry-After: 1` |
| `rate_limit_first` | 同样内容的请求第一次返回 429，之后正常（测试重试） |
| `server_error` | 总是返回 500 |
| `server_error_first` | 同样内容的请求第一次返回 500，之后正常 |
| `timeout` | 挂起 600 秒不返回 |
| `auth` | 返回 401 |
| `not_found` | 返回 404 |
| `context` | 返回 400，错误信息“This model's maximum context length is 8192 tokens” |
| `bad_json` | 返回不是 JSON 的文字，如“好的，我认为这是咨询” |
| `think` | 在内容前加 `<think>演示思考过程……</think>` |
| `reasoning_field` | 把演示思考内容放在 `reasoning_content` 字段 |
| `truncate` | 内容截掉后一半，`finish_reason = "length"` |
| `empty` | 返回空内容 |
| `slow` | 延迟乘以 5 |
| `fast` | 延迟改为 0–5 毫秒（大数据量的性能测试用） |

## 9. 测试连接与获取模型列表

**测试连接**：

- 消息：`[{"role": "user", "content": "请只回复：OK"}]`；
- 最大输出 32（参数名按配置）；温度按模型配置；带上自定义请求头和额外请求体；不发 `response_format`；
- 超时取 `min(timeout_s, 30)` 秒；
- HTTP 200 且有 `choices` 即为成功，`message` 为“连接正常”；内容为空时补一句“，但模型返回了空内容（会思考的模型可能需要更大的最大输出）”；
- 失败时 `message` 用第 6.1 节的中文说明；404 且地址里没有 `/v1` 时补一句“地址可能少了 /v1”；
- 已保存的模型把结果写入 `last_test_*`。

**获取模型列表**：`GET {base_url}/models`，带 `Authorization: Bearer {api_key}`（有密钥时）和自定义请求头；解析 `data[].id`，按字母排序，最多返回 500 个。上游返回 404、405 或格式不对时返回 502 `UPSTREAM_ERROR`，界面提示“这个接口不支持获取模型列表，请手动填写模型名”。
