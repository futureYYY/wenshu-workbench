# 04 接口设计

> 文枢开发文档 · 第 4 篇。后端用 FastAPI 实现，以下定义同时是 Pydantic 模型和前端类型的依据。前端类型不要手写，由 `/openapi.json` 生成（见 02 第 8 节）。

## 1. 约定

- 路径前缀 `/api`；请求和响应都是 `application/json; charset=utf-8`，上传和下载除外。
- 字段一律 `snake_case`。
- 时间一律 UTC ISO 8601 字符串，例如 `"2026-10-21T06:05:09.123Z"`，前端按本地时区显示。
- id 都是整数。
- 列表分页：`?offset=0&limit=50`，`limit` 最大 500，返回 `{ "items": [...], "total": 123 }`。
- 部分更新用 `PATCH`，只传要改的字段。
- 防止其他网页借浏览器调用本机接口：除 `GET`、`OPTIONS` 外的所有 `/api` 请求必须带请求头 `X-WenShu-Client: 1`，否则返回 403 `FORBIDDEN`；`Host` 必须是 `127.0.0.1:{端口}` 或 `localhost:{端口}`，否则返回 403。`/mock` 不受此限制。默认不返回 CORS 头，前端单独部署到其他来源时用环境变量 `WENSHU_CORS_ORIGINS` 放行（CORS 预检是不带自定义请求头的 `OPTIONS`，所以不检查它）。详见 02 第 1.1、10 节。
- 这个请求头在 OpenAPI 里声明为 apiKey 类型的安全方案（位置 header，名称 `X-WenShu-Client`）。在 `/docs` 调试非 GET 接口时，先点 Authorize 填 `1`。
- 所有错误返回统一结构，HTTP 状态码见第 2 节：

```json
{ "error": { "code": "JOB_STATE_CONFLICT", "message": "任务已完成，不能暂停", "detail": {} } }
```

`message` 是可以直接展示给用户的中文。FastAPI 默认的 422 校验错误也要转换成这个结构，`code` 为 `VALIDATION_ERROR`，`detail.fields` 列出每个字段：`[{"path": "concurrency", "message": "必须在 1 到 20 之间"}]`。

下文用 TypeScript 写法描述结构：

```ts
type TaskType   = 'classify' | 'summarize'
type JobStatus  = 'queued' | 'running' | 'paused' | 'completed' | 'cancelled'
type ItemStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'
type ISODateTime = string
interface Page<T> { items: T[]; total: number }
interface ChatMessage { role: 'system' | 'user' | 'assistant'; content: string }
interface ClassifyResult  { label: string; confidence: number | null; reason: string | null }
interface KeyPoint        { text: string; sources: number[] }
interface SummarizeResult { summary: string; key_points: KeyPoint[] }
```

## 2. 错误码

| HTTP | code | 场景 |
|---|---|---|
| 400 | `BAD_REQUEST` | 通用参数错误 |
| 403 | `FORBIDDEN` | 缺少 `X-WenShu-Client` 请求头，或 `Host` 不是本机地址 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `JOB_STATE_CONFLICT` | 任务当前状态不允许该操作 |
| 409 | `MODEL_IN_USE` | 删除仍被排队、运行中或已暂停任务使用的模型 |
| 409 | `MODEL_NAME_TAKEN` | 模型名称重复 |
| 409 | `DEMO_MODEL_PROTECTED` | 删除演示模型，或修改它的固定字段 |
| 409 | `PROMPT_BUILTIN_PROTECTED` | 删除内置模板 |
| 409 | `PROMPT_NAME_TAKEN` | 同一任务类型下模板名称重复 |
| 409 | `FILE_IN_USE` | 删除仍被排队、运行中或已暂停任务使用的文件 |
| 413 | `FILE_TOO_LARGE` | 文件超过 50 MB |
| 415 | `UNSUPPORTED_FILE_TYPE` | 扩展名不支持（P0 中 docx、pdf 也返回这个，message 写“第二期支持”） |
| 422 | `VALIDATION_ERROR` | 字段校验失败 |
| 422 | `LABEL_NOT_IN_PROMPT` | 人工修正的意图不在任务所用提示词列出的类别里，或提示词没有列出类别（05 第 4.6 节）；`detail.labels` 为可选的类别（没有时为空数组） |
| 422 | `FILE_PARSE_FAILED` | 文件损坏、加密或编码无法识别 |
| 422 | `PROMPT_NO_INPUT_VARIABLE` | 用户消息模板没有引用任何输入变量 |
| 422 | `PROMPT_TEMPLATE_MISSING` | 摘要模板缺少分段模板或合并模板，或缺少必需变量 |
| 422 | `NO_ITEMS` | 按所选条件没有可处理的数据 |
| 422 | `MODEL_DISABLED` | 所选模型已停用 |
| 502 | `UPSTREAM_ERROR` | 测试连接、获取模型列表时上游出错；`detail` 含 `status_code`、`error_code` |
| 500 | `INTERNAL_ERROR` | 未预期的错误，`message` 为“内部错误，详情见日志”，日志里有完整堆栈 |

## 3. 系统与设置

### 3.1 系统

| 方法与路径 | 说明 | 返回 |
|---|---|---|
| `GET /api/health` | 健康检查 | `{ "status": "ok", "version": "1.0.0" }` |
| `GET /api/system/info` | 运行信息 | `SystemInfo` |
| `POST /api/system/open-folder` | 用资源管理器打开目录，body `{ "target": "data" \| "logs" \| "exports" }` | 204 |
| `POST /api/system/shutdown` | 暂停所有运行中的任务并退出程序：接口先返回，再通知启动器执行退出流程（07 第 5.1 节第 9 步）。开发模式下只暂停任务，不退出 | 202 `{ "paused_jobs": 1 }` |
| `POST /api/_dev/reset` | **只在开发模式（`WENSHU_DEV=1`）注册**，供端到端测试使用：停止全部任务，清空任务、条目、文件、自建的提示词和模型，设置恢复默认，重新执行启动初始化（03 第 8 节），并重置演示模型的统计（第 11 节） | 204 |

```ts
interface SystemInfo {
  version: string
  data_dir: string          // 绝对路径
  port: number
  open_mode: 'app' | 'browser'
  dev_mode: boolean
  run_mode: 'exe' | 'source' | 'dev'  // 打包版、源码版、开发模式（判断规则见 02 第 9.1 节）
  started_at: ISODateTime
  python_version: string
}
```

### 3.2 设置

| 方法与路径 | 说明 | 返回 |
|---|---|---|
| `GET /api/settings` | 读取全部设置 | `Settings` |
| `PATCH /api/settings` | 部分更新；嵌套对象可只传其中一项，如 `{"default_concurrency": {"classify": 8}}` | `Settings` |

```ts
interface Settings {
  default_concurrency: { classify: number; summarize: number }        // 1–20
  default_limit: number | null                                        // null = 全部
  default_max_retries: number                                         // 0–5
  default_dedupe: boolean
  default_model_id: { classify: number | null; summarize: number | null }
  default_prompt_id: { classify: number; summarize: number }
  theme: 'system' | 'light' | 'dark'
  open_mode: 'app' | 'browser'
  preferred_port: number                                              // 重启后生效
  show_demo_model: boolean
  limits: {                                                           // 只读
    max_concurrency: number          // 20
    max_rows_per_source: number      // 100000
    max_upload_bytes: number         // 52428800
  }
}
```

## 4. 模型配置

```ts
interface ModelConfig {
  id: number
  name: string
  provider_kind: 'openai_compatible' | 'demo'
  base_url: string                     // 规范化后的地址（规则见 05 第 1.2 节）
  request_url: string                  // 实际请求地址：base_url + '/chat/completions'；演示模型为 '本机模拟'
  has_api_key: boolean
  api_key_masked: string | null        // 例如 'sk-…3f9a'；无密钥为 null
  model: string
  temperature: number
  max_output_tokens: number
  max_tokens_param: 'max_tokens' | 'max_completion_tokens'
  context_window: number
  timeout_s: number
  concurrency_cap: number
  json_mode: boolean
  verify_ssl: boolean
  proxy_url: string | null
  extra_headers: Record<string, string>
  extra_body: Record<string, unknown>
  enabled: boolean
  notes: string
  default_for: TaskType[]              // 被设为哪些任务类型的默认模型
  last_test: { at: ISODateTime; ok: boolean; latency_ms: number | null; message: string } | null
  avg_latency_ms: number | null
  active_job_count: number             // 使用它的排队、运行中、已暂停任务数
  created_at: ISODateTime
  updated_at: ISODateTime
}

// POST 时 name、base_url、model 必填；PATCH 时全部可选
interface ModelConfigInput {
  name: string                         // 1–40 字，唯一
  base_url: string                     // 必须以 http:// 或 https:// 开头
  api_key?: string | null              // 语义见下
  model: string                        // 1–200 字
  temperature?: number                 // 0–2
  max_output_tokens?: number           // 16–32768
  max_tokens_param?: 'max_tokens' | 'max_completion_tokens'
  context_window?: number              // 1024–2000000
  timeout_s?: number                   // 5–600
  concurrency_cap?: number             // 1–20
  json_mode?: boolean
  verify_ssl?: boolean
  proxy_url?: string | null            // http:// 或 https:// 开头；null 或空字符串表示直连（05 第 1.1 节）
  extra_headers?: Record<string, string>
  extra_body?: Record<string, unknown>
  enabled?: boolean
  notes?: string
}

interface ModelTestResult {
  ok: boolean
  latency_ms: number | null
  status_code: number | null
  error_code: string | null            // 与 05 第 6 节相同
  message: string                      // 中文结论，如“连接正常”“密钥无效或无权限（HTTP 401）”
  sample_output: string | null         // 返回内容的前 100 字
}
```

**api_key 语义**：

| 接口 | 不传 | 空字符串 | `null` | 非空字符串 |
|---|---|---|---|---|
| `POST /api/models` | 无密钥 | 无密钥 | 无密钥 | 保存 |
| `PATCH /api/models/{id}` | 不改 | 不改 | 清除已保存的密钥 | 替换 |
| `test-draft`、`list-remote` | 给了 `model_id` 时用它已保存的密钥，否则无密钥 | 同“不传” | 无密钥 | 用这个值 |

空字符串一律等同于“不传”，这样编辑表单里密钥框留空时，前端怎么提交都不会误删已保存的密钥。清除密钥只能显式传 `null`，界面上对应“清除密钥”按钮（06 第 6.8 节）。任何接口都不返回明文密钥。

**演示模型**：只允许修改 `name`、`temperature`、`max_output_tokens`、`context_window`、`concurrency_cap`、`enabled`、`notes`，修改其他字段或删除返回 409 `DEMO_MODEL_PROTECTED`。是否在列表里显示由设置 `show_demo_model` 控制。

| 方法与路径 | 说明 | 返回 |
|---|---|---|
| `GET /api/models` | 列表；`show_demo_model` 为 false 时不含演示模型，加 `?include_demo=true` 强制包含 | `{ items: ModelConfig[] }` |
| `POST /api/models` | 新建 | 201 `ModelConfig` |
| `GET /api/models/{id}` | 详情 | `ModelConfig` |
| `PATCH /api/models/{id}` | 修改 | `ModelConfig` |
| `DELETE /api/models/{id}` | 删除；如果它是默认模型，对应设置改为 `null` | 204；409 `MODEL_IN_USE` |
| `POST /api/models/{id}/test` | 用已保存的配置测试，并把结果写入 `last_test_*` | `ModelTestResult` |
| `POST /api/models/test-draft` | 测试尚未保存的配置，不写库。body `{ config: ModelConfigInput, model_id?: number }`；密钥按上表取 | `ModelTestResult` |
| `POST /api/models/list-remote` | 获取上游模型列表。body 同 `test-draft` | `{ models: string[] }`；上游不支持时 502 `UPSTREAM_ERROR` |

测试连接和获取列表的实现见 05 第 9 节。测试失败不是接口错误：`test` 和 `test-draft` 永远返回 200，用 `ok` 表示结果。

## 5. 提示词

```ts
interface ClassifyFieldMap  { label: string; confidence: string | null; reason: string | null }
interface SummarizeFieldMap { summary: string; key_points: string | null }

interface PromptTemplate {
  id: number
  task_type: TaskType
  name: string
  description: string
  system_prompt: string
  user_template: string
  chunk_template: string | null        // 仅 summarize
  merge_template: string | null        // 仅 summarize
  output_mode: 'json' | 'text'
  field_map: ClassifyFieldMap | SummarizeFieldMap
  temperature: number | null
  max_output_tokens: number | null
  is_builtin: boolean
  builtin_key: string | null
  version: number
  is_default: boolean
  used_by_jobs: number                 // 引用它的任务数
  created_at: ISODateTime
  updated_at: ISODateTime
}

// 试运行和渲染使用的“草稿”，不需要先保存
interface PromptDraft {
  task_type: TaskType
  system_prompt: string
  user_template: string
  chunk_template?: string | null
  merge_template?: string | null
  output_mode: 'json' | 'text'
  field_map: ClassifyFieldMap | SummarizeFieldMap
  temperature?: number | null
  max_output_tokens?: number | null
}

interface PromptInput extends PromptDraft {
  name: string                         // 1–40 字，同一任务类型下唯一
  description?: string                 // ≤ 200 字
  note?: string                        // 本次保存的版本说明，≤ 100 字
}

interface PromptVariable {
  name: string                         // 如 'text'、'col:列名'
  insert: string                       // 插入编辑器的文本，如 '{{text}}'
  description: string                  // 中文说明
  templates: ('system' | 'user' | 'chunk' | 'merge')[]   // 可以用在哪些模板里
}

// 试运行和渲染的样本：直接给文本，或指定已上传文件的某一行
type Sample =
  | { kind: 'text'; text: string }
  | { kind: 'row'; file_id: number; sheet: string | null; header_row: number;
      text_columns: string[]; join_mode: 'labeled' | 'plain'; row_number: number }
```

| 方法与路径 | 说明 | 返回 |
|---|---|---|
| `GET /api/prompts?task_type=classify` | 列表；默认模板在最前，其次内置，其余按修改时间倒序 | `{ items: PromptTemplate[] }` |
| `POST /api/prompts` | 新建。body 为 `PromptInput`，或 `{ copy_from_id: number, name?: string }`（复制，名称默认“原名 副本”） | 201 `PromptTemplate`（version 1） |
| `GET /api/prompts/{id}` | 详情 | `PromptTemplate` |
| `PUT /api/prompts/{id}` | 保存。body 为 `PromptInput`，`task_type` 必须与原模板相同。内容字段有变化时版本号 +1 并写入 `prompt_versions`；只改名称或说明时不产生新版本 | `PromptTemplate` |
| `DELETE /api/prompts/{id}` | 删除；若是默认模板，默认改回该类型的内置模板。已有任务保留快照不受影响 | 204；409 `PROMPT_BUILTIN_PROTECTED` |
| `GET /api/prompts/{id}/versions` | 版本列表，新的在前 | `{ items: { version, note, created_at }[] }` |
| `GET /api/prompts/{id}/versions/{version}` | 某个版本的完整内容 | `{ version, note, created_at, snapshot }`，`snapshot` 结构见 03 第 4.3 节 |
| `POST /api/prompts/{id}/restore` | body `{ version: number }`，把该版本内容存为新版本，说明自动写“恢复自 v{n}” | `PromptTemplate` |
| `POST /api/prompts/{id}/reset-builtin` | 仅内置模板：把出厂内容存为新版本，说明写“恢复内置默认” | `PromptTemplate` |
| `GET /api/prompts/variables?task_type=` | 编辑器补全用的变量清单（见 05 第 2.2 节）。`col:列名` 以 `col:` 一项表示 | `{ items: PromptVariable[] }` |
| `POST /api/prompts/render` | 按样本渲染出实际消息。body `{ prompt: PromptDraft, sample: Sample, stage?: 'main' \| 'chunk' \| 'merge' }` | `{ messages: ChatMessage[], unknown_variables: string[], estimated_input_tokens: number }` |

**保存时的校验**（POST、PUT，不通过返回 422）：

1. `user_template` 至少引用 `{{text}}`、`{{text_numbered}}`、`{{row_json}}`、`{{col:…}}` 之一，否则 `PROMPT_NO_INPUT_VARIABLE`；
2. 摘要模板：`chunk_template`、`merge_template` 都不能为空；`chunk_template` 必须含 `{{text}}` 或 `{{text_numbered}}`；`merge_template` 必须含 `{{chunk_summaries}}`。否则 `PROMPT_TEMPLATE_MISSING`；
3. `output_mode = 'json'` 时，意图识别必须有 `field_map.label`，摘要必须有 `field_map.summary`，否则 `VALIDATION_ERROR`；
4. 未知变量不阻止保存，由编辑器标出（前端用变量清单自行检查）。

## 6. 试运行

`POST /api/playground/run`，返回 `text/event-stream`。

body：

```ts
{ prompt: PromptDraft; model_id: number; sample: Sample }
```

事件（`event:` 为名称，`data:` 为 JSON）：

| 事件 | data | 说明 |
|---|---|---|
| `stage` | `{ name: 'request' \| 'chunk' \| 'merge'; index?: number; total?: number }` | 进入一个阶段；摘要分段时依次为 chunk 1/n…、merge |
| `delta` | `{ content: string }` | 当前阶段输出的增量文本 |
| `reasoning_delta` | `{ content: string }` | 思考内容的增量（模型提供时） |
| `done` | 见下 | 全部完成 |
| `error` | `{ error_code: string; message: string; status_code: number \| null }` | 出错并结束 |

```ts
interface PlaygroundDone {
  raw_output: string                   // 最后一个阶段的原始输出
  reasoning: string | null
  parsed: ClassifyResult | SummarizeResult | null
  parse_error: string | null           // 解析失败的中文原因
  usage: { prompt_tokens: number; completion_tokens: number }   // 各阶段合计
  latency_ms: number                   // 各阶段合计
  chunk_count: number
  truncated: boolean
  messages: ChatMessage[]              // 最后一个阶段实际发送的消息
}
```

- 各事件的 data 结构登记在 OpenAPI 的 components 里，名字依次为 `PlaygroundStageEvent`、`PlaygroundDeltaEvent`（`delta` 和 `reasoning_delta` 共用）、`PlaygroundDone`、`PlaygroundErrorEvent`（第 10.1 节）；
- 试运行不自动重试，出错直接返回 `error`；
- 客户端断开连接时，服务端取消上游请求；
- 上游不支持流式（返回 400 且错误信息提到 stream）时，自动改用非流式请求，把完整内容作为一个 `delta` 发出。

## 7. 文件

```ts
interface FileInfo {
  id: number
  original_name: string
  ext: 'txt' | 'md' | 'csv' | 'xlsx' | 'xls' | 'docx' | 'pdf'
  size_bytes: number
  source: 'upload' | 'paste'
  encoding: string | null
  delimiter: string | null
  kind: 'table' | 'lines'
  sheets: { name: string; row_count: number; truncated: boolean }[]   // lines 类为空数组
  line_count: number | null                                           // 仅 lines 类
  truncated: boolean                                                  // 任一部分被截断
  created_at: ISODateTime
  last_used_at: ISODateTime
  reused: boolean                     // 上传、粘贴接口返回：内容与已有文件相同，直接复用了已有记录（名称沿用已有记录的）
}

interface ColumnInfo {
  key: string
  title: string
  letter: string | null               // lines 类为 null
  index: number
  avg_chars: number                   // 预览范围内非空值的平均字数
  empty_ratio: number                 // 预览范围内空值占比，0–1
  numeric_ratio: number               // 预览范围内纯数字或日期的占比，0–1
}

interface FilePreview {
  sheet: string | null
  header_row: number
  columns: ColumnInfo[]
  suggested_text_columns: string[]    // 推荐的文本列：numeric_ratio < 0.5 中 avg_chars 最大的一列
  rows: { row_number: number; values: Record<string, string> }[]
  total_rows: number                  // 数据行数（不含表头、含空行）
  blank_rows: number                  // 整行全空的行数
  truncated: boolean
}
```

| 方法与路径 | 说明 | 返回 |
|---|---|---|
| `POST /api/files` | `multipart/form-data`，字段名 `file` | 201 `FileInfo`；内容相同已存在时 200 且 `reused: true` |
| `POST /api/files/paste` | body `{ text: string, name?: string }`，存成 UTF-8 txt，名称默认“粘贴文本 2026-10-21 14:05”（本地时间）。和上传一样按内容哈希判断重复 | 201 `FileInfo`；内容相同已存在时 200 且 `reused: true` |
| `GET /api/files` | 最近使用的文件，按 `last_used_at` 倒序 | `Page<FileInfo>` |
| `GET /api/files/{id}` | 详情 | `FileInfo` |
| `GET /api/files/{id}/preview` | 参数：`sheet`（表格类必填）、`header_row`（默认 1，lines 类忽略）、`offset`（默认 0）、`limit`（默认 200，最大 500） | `FilePreview` |
| `DELETE /api/files/{id}` | 删除记录和磁盘文件。已完成或已取消的任务不受影响（它们的条目自带原文） | 204；409 `FILE_IN_USE` |

上传错误：超过 50 MB 返回 413 `FILE_TOO_LARGE`（在读完请求体之前就拒绝）；扩展名不支持返回 415；解析失败返回 422 `FILE_PARSE_FAILED`，`message` 写清原因，例如“这个 Excel 文件设置了打开密码”“无法识别文件编码”。解析规则见 02 第 6 节。

## 8. 任务

```ts
interface JobSourceInput {
  sheet: string | null
  header_row: number                  // 0 = 无表头
  text_columns: string[]              // 至少 1 个
  join_mode: 'labeled' | 'plain'
  start_row: number | null
  limit: number | null                // null = 全部；否则 1–100000
  split_mode: 'line'
}

interface JobCreate {
  name?: string                       // 不传则为“文件名（去扩展名） 意图识别/文本摘要”
  task_type: TaskType
  file_id: number
  source: JobSourceInput
  prompt_id: number                   // 必须与 task_type 相同类型
  model_id: number
  concurrency: number                 // 1–20
  max_retries?: number                // 不传取设置 default_max_retries
  dedupe?: boolean                    // 不传取设置 default_dedupe
}

interface JobEstimate {
  item_count: number                  // 将要处理的非空条目数
  skipped_empty: number               // 范围内文本为空、将被跳过的行数
  duplicate_count: number             // 开启去重时省下的请求数（按去重键计算，03 第 4.7 节）
  request_count: number               // item_count − duplicate_count（不含分段带来的额外请求）
  long_text_count: number             // 超出上下文、需要截断（识别）或分段（摘要）的条目数
  est_prompt_tokens: number
  est_completion_tokens: number
  est_seconds: [number, number]       // 预计耗时区间
  warnings: string[]                  // 中文提醒，如“提示词里有未知变量 {{foo}}”
}

interface JobProgress {
  total: number; pending: number; running: number
  succeeded: number; failed: number; skipped: number
  percent: number                     // 0–100，1 位小数
  rate_per_min: number | null
  eta_seconds: number | null
}

interface JobSummary {
  id: number
  name: string
  task_type: TaskType
  status: JobStatus
  status_reason: string
  status_reason_code: 'user_pause' | 'shutdown' | 'auth_failed' | 'model_not_found'
                    | 'circuit_breaker' | 'write_failed' | null   // 03 第 6.1 节；界面按它决定提示和操作
  file_name: string
  model_name: string                  // 来自快照
  prompt_name: string
  prompt_version: number
  concurrency: number
  progress: JobProgress
  created_at: ISODateTime
  started_at: ISODateTime | null
  finished_at: ISODateTime | null
  updated_at: ISODateTime
}

interface CategoryStat {
  label: string                       // 有效类别
  count: number
  percent: number                     // 占已成功条目的百分比，1 位小数
  color_index: number                 // 0–10；-1 表示“其他”灰色
}

// 实时推送用：JobSummary + 统计，不含快照
interface JobLive extends JobSummary {
  usage: { prompt_tokens: number; completion_tokens: number }
  categories: CategoryStat[] | null   // 仅 classify，按 count 降序
  compression: { input_chars: number; output_chars: number; ratio: number | null } | null   // 仅 summarize，已成功条目合计（按有效摘要字数，03 第 7 节）
}

interface Job extends JobLive {
  file_id: number | null
  source: JobSourceInput & { columns: { key: string; title: string; letter: string | null; index: number }[] }
  prompt_id: number | null
  prompt_snapshot: object             // 结构见 03 第 4.3 节
  model_id: number | null
  model_snapshot: object              // 结构见 03 第 4.3 节
  max_retries: number
  dedupe: boolean
  label_options: string[]             // 意图识别：任务所用提示词（快照）里列出的类别，按出现顺序（05 第 4.6 节）；人工修正只能改成这些。摘要任务、或提示词没有列出类别时为空数组
}

interface ItemSummary {
  id: number
  seq: number
  row_number: number
  status: ItemStatus
  input_preview: string               // 前 200 字，换行替换为空格
  input_chars: number
  label: string | null
  effective_label: string | null      // 有效类别（03 第 7 节）：人工修正过的取修正后的
  manual_label: string | null         // 人工修正的意图；没有修正为 null，这时 effective_label 来自模型（label）
  corrected: boolean                  // 意图或摘要有人工修正
  confidence: number | null
  reason: string | null
  summary_preview: string | null      // 有效摘要（人工修改过的取修改后的）主旨前 200 字
  output_chars: number | null         // 有效摘要加要点的字数（03 第 7 节）
  compression_ratio: number | null    // input_chars / output_chars
  truncated: boolean
  chunk_count: number
  attempts: number
  latency_ms: number | null
  error_code: string | null
  error_message: string | null
  reviewed: boolean
  dedup_of: number | null
  finished_at: ISODateTime | null
}

interface AttemptLogEntry {
  at: ISODateTime; attempt: number; phase: string
  status_code: number | null; error_code: string | null
  message: string; latency_ms: number | null
}

interface ItemDetail extends ItemSummary {
  input_text: string
  row_values: Record<string, string>
  segments: string[] | null           // 仅摘要：按 05 第 7.2 节切分出的段落；sources 里的编号 n 对应 segments[n-1]
  summary: string | null              // 模型输出的摘要主旨（人工修改不会改变它）
  manual_summary: string | null       // 人工修改后的摘要主旨；没有修改为 null
  key_points: KeyPoint[] | null
  result: Record<string, unknown> | null
  raw_output: string | null
  reasoning: string | null
  messages: ChatMessage[]             // 按任务快照和该条目的 render_meta（03 第 4.7 节）重新渲染，与当时实际发送的一致；分段时为第一段的消息；还没处理过的条目按当前模型配置渲染
  omitted_chars: number | null        // 意图识别截断时省略的字数
  attempt_log: AttemptLogEntry[]
  model_used: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  note: string | null
  manual_at: ISODateTime | null       // 最近一次人工修正（意图或摘要）的时间；没有修正为 null
  started_at: ISODateTime | null
}

interface Track {                     // 并行轨道上的一个槽
  item_id: number
  seq: number
  row_number: number
  input_preview: string               // 前 60 字
  started_at: ISODateTime
  attempt: number                     // 当前是第几次请求
  phase: 'request' | 'waiting_retry' | 'chunk' | 'merge' | 'parse_repair'
  phase_detail: string                // 如“限流，3 秒后重试”“第 2/5 段”；普通请求为空字符串
  retry_at: ISODateTime | null
}
```

### 8.1 任务接口

| 方法与路径 | 说明 | 返回 |
|---|---|---|
| `POST /api/jobs/estimate` | 预估，body 同 `JobCreate`，不写库 | `JobEstimate`；422 `NO_ITEMS` |
| `POST /api/jobs` | 创建并立即开始 | 201 `Job`；422 `NO_ITEMS`、`MODEL_DISABLED` |
| `GET /api/jobs` | 列表，参数：`status`（逗号分隔多个）、`task_type`、`q`（搜任务名和文件名）、`offset`、`limit`；按创建时间倒序 | `Page<JobSummary>` |
| `GET /api/jobs/{id}` | 详情 | `Job` |
| `PATCH /api/jobs/{id}` | body `{ name?: string, concurrency?: number }`；运行中改并发是 P1，P0 只在非运行状态下允许改并发 | `Job` |
| `POST /api/jobs/{id}/pause` | 仅 queued、running | `Job`；否则 409 |
| `POST /api/jobs/{id}/resume` | 仅 paused。暂停前派发的条目还在收尾时，复用那个执行器，不会叠加并发（02 第 5.4 节）；已经没有待处理条目时直接转为 completed | `Job`；否则 409 |
| `POST /api/jobs/{id}/cancel` | 仅 queued、running、paused | `Job`；否则 409 |
| `POST /api/jobs/{id}/retry-failed` | 仅 completed、paused 且有失败条目；把失败条目置为 pending 并开始运行 | `Job`；否则 409 |
| `DELETE /api/jobs/{id}` | 仅 completed、cancelled、paused；级联删除条目 | 204；否则 409 |

暂停接口立刻返回，此时任务状态已是 `paused`，但进行中的条目还会继续完成，`progress.running` 逐渐降到 0。

### 8.2 条目接口

| 方法与路径 | 说明 | 返回 |
|---|---|---|
| `GET /api/jobs/{id}/items` | 见下方参数 | `Page<ItemSummary>` |
| `GET /api/jobs/{id}/items/{item_id}` | 详情 | `ItemDetail` |
| `PATCH /api/jobs/{id}/items/{item_id}` | 人工复核，body `{ manual_label?: string \| null, manual_summary?: string \| null, reviewed?: boolean, note?: string \| null }`，规则见下方 | `ItemSummary`；409 `JOB_STATE_CONFLICT`（条目还没处理成功）；422 `LABEL_NOT_IN_PROMPT`、`VALIDATION_ERROR` |
| `POST /api/jobs/{id}/items/{item_id}/rerun` | 单条重新处理：置为 pending；任务为 completed 时转为 running，为 running 时由执行器排队处理，为 paused 时保持暂停；任务为 cancelled、或这一条正在处理时返回 409。只重置模型结果，人工修正和复核标记保留 | `ItemSummary` |
| `GET /api/jobs/{id}/categories` | 类别统计（仅 classify） | `{ items: CategoryStat[], failed: number }` |
| `POST /api/jobs/{id}/categories/merge` | P1。body `{ from: string[], to: string }`，写入别名表 | `{ items: CategoryStat[], failed: number }` |
| `GET /api/jobs/{id}/tracks` | 当前并行轨道（进入页面时的初始数据，之后靠 SSE 更新） | `{ items: Track[] }` |

`items` 列表参数：

| 参数 | 说明 |
|---|---|
| `status` | 逗号分隔多个，如 `failed,skipped` |
| `label` | 按有效类别筛选，可重复传多个：`label=物流查询&label=退款咨询` |
| `q` | 关键词，匹配原文、类别（含人工修正的）、判断依据、摘要（含人工修改的） |
| `reviewed` | `true` / `false`：是否已复核 |
| `corrected` | `true` / `false`：意图或摘要是否有人工修正 |
| `order` | `seq`（默认）、`-seq`、`confidence`、`-confidence`、`latency_ms`、`-latency_ms`、`input_chars`、`-input_chars` |
| `offset`、`limit` | 分页，`limit` 最大 500 |

**人工复核**（`PATCH /api/jobs/{id}/items/{item_id}`，01 RES-06、RES-07、RES-11）：

- 只传要改的字段。`manual_label`、`manual_summary` 传 `null` 表示撤销修正，撤销不限条目状态；
- `manual_label` 只用于意图识别任务，`manual_summary` 只用于文本摘要任务，传错返回 422 `VALIDATION_ERROR`；
- 设置修正时条目必须是 succeeded，否则返回 409 `JOB_STATE_CONFLICT`（“只有处理成功的条目可以人工修正”）；任务处于什么状态都可以；
- `manual_label` 先按 05 第 4.5 节规范化，必须是 `Job.label_options` 里的一个，否则返回 422 `LABEL_NOT_IN_PROMPT`：message 列出可选的类别，提示词没有列出类别时说明原因；与模型的 `label` 相同视为撤销（存为 null）；修正成模型没给过的类别时，同样按 03 第 4.6 节分配线路色；
- `manual_summary` 去掉首尾空白后不能为空（422 `VALIDATION_ERROR`），最长 10,000 字；与模型的 `summary` 相同视为撤销；要点保持模型输出；
- 设置修正（不是撤销）时自动把 `reviewed` 置为 true；同一请求里明确给了 `reviewed` 时以请求为准。`reviewed` 单独修改不限条目状态；
- `manual_at` 记最近一次修正的时间，没有修正时为 null；
- 修改后发布 `job.updated`（线网图、浓缩计按修正后的值统计）和 `items.updated`。

## 9. 导出

`GET /api/jobs/{id}/export?format=xlsx&scope=all`

| 参数 | 说明 |
|---|---|
| `format` | `xlsx`、`csv`；P1 增加 `json` |
| `scope` | `all`（全部条目）或 `filtered`（同时传第 8.2 节的筛选参数） |

返回文件流，`Content-Disposition: attachment; filename*=UTF-8''<URL 编码的文件名>`。文件名：`{原文件名去扩展名}_{意图识别|文本摘要}_{YYYYMMDD-HHmm}.{扩展名}`，时间为本地时间。

**行**：按 `seq` 顺序输出范围内所有条目，包括失败、跳过和未处理的。

**列**：先输出原始列，再输出结果列。

- 表格类的原始列：按 `source.columns` 的顺序，表头用列标题；
- 文本类的原始列：`行号`、`文本`；
- 结果列与原始列重名时，结果列加后缀“（文枢）”。

| 任务类型 | 结果列 |
|---|---|
| 意图识别 | `意图`（有效类别）、`修正前意图`（人工修正过时为模型给出的类别，否则为空）、`置信度`（两位小数）、`判断依据`、`人工修正`（是/空）、`已复核`（是/空）、`处理状态`、`错误信息` |
| 文本摘要 | `摘要`（有效摘要）、`修正前摘要`（人工修改过时为模型给出的摘要，否则为空）、`关键要点`、`原文字数`、`摘要字数`（有效摘要加要点的字数）、`压缩比`、`人工修正`（是/空）、`已复核`（是/空）、`处理状态`、`错误信息` |

- `处理状态` 取值：成功、失败、跳过、未处理（pending 或 running）；
- `关键要点` 每条一行，格式 `1. 要点内容（第 2、5 段）`，没有来源时省略括号；
- 去重的跟随条目照常输出各自的一行。

**xlsx 格式**：第一个工作表名“结果”，表头加粗、浅灰底色 `#EEF2F6`、冻结首行；列宽按内容估算，最小 10、最大 60 个字符；文本类列自动换行；置信度用数字格式 `0.00`。第二个工作表名“任务信息”，两列（项目、内容），写入任务名、文件名、任务类型、模型名和模型、提示词名和版本、并发、开始和结束时间、各状态条数、tokens 合计。

**csv 格式**：UTF-8 带 BOM，逗号分隔，CRLF 换行，按需加引号。

**单元格清理**（两种格式都要做，防止导出失败或被 Excel 当成公式执行）：

- 去掉 Excel 不允许的控制字符（`\x00`–`\x08`、`\x0b`、`\x0c`、`\x0e`–`\x1f`），可直接用 openpyxl 的 `ILLEGAL_CHARACTERS_RE`；否则 openpyxl 会抛 `IllegalCharacterError`，导出变成 500；
- xlsx：除置信度、字数、压缩比这几个数值列外，所有单元格一律按文本写入（单元格 `data_type` 设为 `"s"`）。以 `=` 开头的文本不能被写成公式；
- csv：值以 `=`、`+`、`-`、`@`、制表符或回车开头、且不是纯数字时，在前面加一个英文单引号 `'`；
- 单元格超过 32,767 字（Excel 上限）时截断，并在末尾加“……（已截断）”。

导出文件先写到 `data/exports/`，再作为响应返回；超过 1 万行时分页读取、流式写出，不一次性加载。

## 10. 实时事件（SSE）

`GET /api/events`：全局事件流，用于首页和任务中心。
`GET /api/events?job_id={id}`：单个任务的事件流，用于任务详情页。

格式：

```
event: job.updated
id: 1042
data: {"id": 7, "status": "running", ...}

```

| 事件 | 所在流 | data | 频率 |
|---|---|---|---|
| `job.created` | 全局 | `JobSummary` | 创建时 |
| `job.updated` | 全局 | `JobSummary` | 状态变化时立即发；运行中每秒最多 1 次 |
| `job.deleted` | 全局 | `{ job_id: number }` | 删除时 |
| `job.updated` | 单任务 | `JobLive` | 同上 |
| `items.updated` | 单任务 | `{ job_id: number, items: ItemSummary[] }` | 每 250 毫秒合并发送一次，单次最多 200 条，超出拆成多个事件 |
| `tracks.updated` | 单任务 | `{ job_id: number, items: Track[] }` | 运行中每 250 毫秒，内容有变化才发 |
| `ping` | 两者 | `{}` | 每 15 秒 |

- `id` 单调递增，但服务端不做断线补发；
- 客户端断线重连成功后，重新请求任务详情和当前可见的那一页条目，用接口数据覆盖本地状态；
- 只有写入协程把状态落库后才发事件（见 03 第 9 节）；
- `ping` 必须是具名事件（`event: ping`）。sse-starlette 默认发的是注释行，前端监听不到，要用它的 `ping_message_factory` 改成具名事件（02 第 7 节）。

### 10.1 事件数据的类型

SSE 和试运行的事件数据不出现在任何普通接口的响应里，FastAPI 默认不会把它们写进 OpenAPI，前端也就生成不出类型。后端要自定义 `app.openapi()`，把下列模型显式登记到 `components.schemas`（用 Pydantic 的 `TypeAdapter(模型).json_schema(ref_template="#/components/schemas/{model}")` 生成，并把其中的 `$defs` 一并并入）。前端从生成的 `components["schemas"]` 里取这些类型，不手写。

| 事件 | 登记的模型名 |
|---|---|
| 全局 `job.created`、`job.updated` | `JobSummary` |
| 单任务 `job.updated` | `JobLive` |
| `job.deleted` | `JobDeletedEvent` |
| `items.updated` | `ItemsUpdatedEvent` |
| `tracks.updated` | `TracksUpdatedEvent` |
| `ping` | `PingEvent` |
| 试运行 `stage` | `PlaygroundStageEvent` |
| 试运行 `delta`、`reasoning_delta` | `PlaygroundDeltaEvent` |
| 试运行 `done` | `PlaygroundDone` |
| 试运行 `error` | `PlaygroundErrorEvent` |

## 11. 演示模型接口

演示模型是程序内置的一个 OpenAI 兼容接口，挂在同一个服务上，不需要密钥。任务引擎调用演示模型时，和调用真实模型走完全相同的 HTTP 路径（地址为 `http://127.0.0.1:{当前端口}/mock/v1`），保证测试覆盖真实的调用链路。

| 方法与路径 | 说明 |
|---|---|
| `POST /mock/v1/chat/completions` | 兼容 Chat Completions 的常用子集：`model`、`messages`、`temperature`、`max_tokens`、`max_completion_tokens`、`stream`、`response_format`。返回 `choices[0].message.content`、`finish_reason`、`usage` |
| `GET /mock/v1/models` | `{"object": "list", "data": [{"id": "wenshu-demo", "object": "model"}]}` |
| `GET /mock/v1/_stats` | 统计，供测试和验收使用：`{"inflight": 3, "max_inflight": 8, "total": 1042, "by_status": {"200": 1030, "429": 12}}`。`inflight` 是正在处理的请求数，`max_inflight` 是上次重置以来的最大值 |
| `POST /mock/v1/_reset` | 清零统计，并清空“首次请求”的记录（05 第 8.5 节）；返回 204 |

生成内容的规则、请求头 `X-Mock-Behavior` 控制的故障模拟见 05 第 8 节。

## 12. 静态资源与前端路由

- 前端构建产物放在 `backend/app/static/`，由同一个服务提供；
- 带哈希的资源（`/assets/*`）返回 `Cache-Control: public, max-age=31536000, immutable`；`index.html` 返回 `Cache-Control: no-cache`；
- 其他 GET 请求（不以 `/api`、`/mock`、`/docs`、`/docs-assets`、`/openapi.json` 开头的）：先看 `static` 目录下有没有这个文件（例如 `/favicon.svg`、`/assets/…`），有就直接返回；没有才返回 `index.html`，交给前端路由。解析路径时要防止 `..` 跳出 `static` 目录；
- `backend/app/static` 不存在时（只跑后端、或前端还没构建），这些请求返回 200 的纯文字说明“前端尚未构建。运行 scripts\build-web.bat 构建，或用 scripts\dev.bat 开发。”，接口不受影响；
- `/docs`（Swagger UI）始终开启，方便调试。不用 FastAPI 默认从 CDN 加载的版本（离线或国内网络下常常白屏）：构造应用时设 `docs_url=None`，自己注册 `/docs`，用 `get_swagger_ui_html(...)` 指向随后端分发的 `/docs-assets/swagger-ui-bundle.js` 和 `/docs-assets/swagger-ui.css`（来源见 02 第 2.2 节），并设 `swagger_ui_parameters={"persistAuthorization": True}`，Authorize 填过一次后刷新页面不用重填。

前端路由（Vue Router，history 模式）：

| 路径 | 页面 |
|---|---|
| `/` | 首页 |
| `/new` | 新建任务；`?file=12` 表示带着已上传的文件进入 |
| `/jobs` | 任务中心 |
| `/jobs/:id` | 任务详情；`?item=501` 打开条目抽屉；`?label=物流查询` 预设筛选 |
| `/jobs/:id/read/:itemId` | 摘要对照阅读 |
| `/prompts`、`/prompts/:id` | 提示词工坊（不带 id 时进入意图识别的默认模板） |
| `/models` | 模型接入；`?edit=3` 打开编辑抽屉，`?new=1` 打开新建抽屉 |
| `/settings` | 设置 |
