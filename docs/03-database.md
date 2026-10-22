# 03 数据库设计

> 文枢开发文档 · 第 3 篇。本文与 04（接口）是字段命名的唯一依据，其他文档与之冲突时以这两篇为准。

## 1. 概览

- 数据库：SQLite 单文件 `data/wenshu.db`，WAL 模式。
- 访问：SQLAlchemy 2（异步）+ aiosqlite。业务代码不直接拼 SQL 字符串，统一走 `app/db/` 下的仓储函数。
- 时间：一律存 UTC 的 ISO 8601 字符串，精确到毫秒，带 `Z`，例如 `2026-10-21T06:05:09.123Z`。接口原样返回，前端按本地时区显示。
- 布尔：存 `INTEGER` 0/1，接口返回 `true/false`。
- JSON：存 `TEXT`，字段名以 `_json` 结尾；接口返回时去掉后缀并解析成对象，例如 `extra_headers_json` → `extra_headers`。

```
settings            键值设置

model_configs ──┐
                ├──< jobs >──── files
prompt_templates┘     │
     │                └──< job_items（每行一条）
     └──< prompt_versions
```

## 2. 连接设置

每个新连接执行：

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA temp_store = MEMORY;
```

**新建数据库文件时**（文件还不存在），第一个连接必须**先**执行 `PRAGMA auto_vacuum = INCREMENTAL;`，再执行上面的设置。顺序反过来的话，切换到 WAL 时文件已经建好，auto_vacuum 实际仍为 0，删除任务后空间回收不了。之后的连接只执行上面的设置。删除任务后执行 `PRAGMA incremental_vacuum;` 回收空间；第 8 节初始化时检查 `PRAGMA auto_vacuum` 是否为 2（INCREMENTAL），不是则记一条警告日志。

## 3. 表结构

迁移文件 `backend/app/db/migrations/0001_init.sql` 的完整内容如下。

```sql
-- ============ 设置 ============
CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value_json  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

-- ============ 模型配置 ============
CREATE TABLE model_configs (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  name                  TEXT    NOT NULL UNIQUE,              -- 显示名，如“DeepSeek”
  provider_kind         TEXT    NOT NULL DEFAULT 'openai_compatible'
                        CHECK (provider_kind IN ('openai_compatible', 'demo')),
  base_url              TEXT    NOT NULL,                     -- 规范化后的地址，不含 /chat/completions；演示模型为 'demo://local'
  api_key_enc           TEXT,                                 -- Fernet 密文；无密钥时为 NULL
  api_key_last4         TEXT,                                 -- 掩码用的末 4 位
  model                 TEXT    NOT NULL,                     -- 请求里的 model 字段
  temperature           REAL    NOT NULL DEFAULT 0.3,         -- 0–2
  max_output_tokens     INTEGER NOT NULL DEFAULT 1024,        -- 16–32768
  max_tokens_param      TEXT    NOT NULL DEFAULT 'max_tokens'
                        CHECK (max_tokens_param IN ('max_tokens', 'max_completion_tokens')),
  context_window        INTEGER NOT NULL DEFAULT 32768,       -- 1024–2000000
  timeout_s             INTEGER NOT NULL DEFAULT 120,         -- 5–600
  concurrency_cap       INTEGER NOT NULL DEFAULT 20
                        CHECK (concurrency_cap BETWEEN 1 AND 20),
  json_mode             INTEGER NOT NULL DEFAULT 0,           -- 1 = 发送 response_format: json_object
  verify_ssl            INTEGER NOT NULL DEFAULT 1,
  proxy_url             TEXT,                                 -- 如 http://127.0.0.1:7890；NULL 表示不用代理
  extra_headers_json    TEXT    NOT NULL DEFAULT '{}',        -- {"X-App-Id": "..."}
  extra_body_json       TEXT    NOT NULL DEFAULT '{}',        -- {"enable_thinking": false}
  enabled               INTEGER NOT NULL DEFAULT 1,
  notes                 TEXT    NOT NULL DEFAULT '',
  last_test_at          TEXT,
  last_test_ok          INTEGER,
  last_test_latency_ms  INTEGER,
  last_test_message     TEXT,
  avg_latency_ms        INTEGER,                              -- 最近成功调用耗时的滑动平均，用于预估
  created_at            TEXT    NOT NULL,
  updated_at            TEXT    NOT NULL                      -- 只在用户新建、修改配置时更新；写测试结果和平均耗时不更新（05 第 1.3 节用它做缓存键）
);

-- ============ 提示词模板 ============
CREATE TABLE prompt_templates (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  task_type          TEXT    NOT NULL CHECK (task_type IN ('classify', 'summarize')),
  name               TEXT    NOT NULL,
  description        TEXT    NOT NULL DEFAULT '',
  system_prompt      TEXT    NOT NULL,
  user_template      TEXT    NOT NULL,
  chunk_template     TEXT,                                    -- 仅 summarize：分段摘要用
  merge_template     TEXT,                                    -- 仅 summarize：合并各段摘要用
  output_mode        TEXT    NOT NULL DEFAULT 'json' CHECK (output_mode IN ('json', 'text')),
  field_map_json     TEXT    NOT NULL DEFAULT '{}',           -- 见第 4.4 节
  temperature        REAL,                                    -- 覆盖模型默认值，NULL 表示不覆盖
  max_output_tokens  INTEGER,                                 -- 同上
  is_builtin         INTEGER NOT NULL DEFAULT 0,
  builtin_key        TEXT    UNIQUE,                          -- 'classify.default' | 'summarize.default'
  version            INTEGER NOT NULL DEFAULT 1,              -- 当前版本号，每次保存 +1
  created_at         TEXT    NOT NULL,
  updated_at         TEXT    NOT NULL,
  UNIQUE (task_type, name)
);

CREATE TABLE prompt_versions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_id      INTEGER NOT NULL REFERENCES prompt_templates(id) ON DELETE CASCADE,
  version        INTEGER NOT NULL,
  snapshot_json  TEXT    NOT NULL,                            -- 该版本全部可编辑字段，见第 4.3 节
  note           TEXT    NOT NULL DEFAULT '',                 -- 保存时填写的说明，可空
  created_at     TEXT    NOT NULL,
  UNIQUE (prompt_id, version)
);

-- ============ 上传文件 ============
CREATE TABLE files (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  original_name  TEXT    NOT NULL,
  stored_path    TEXT    NOT NULL,                            -- 相对 data 目录，如 uploads/ab/ab12…ef.xlsx
  ext            TEXT    NOT NULL CHECK (ext IN ('txt', 'md', 'csv', 'xlsx', 'xls', 'docx', 'pdf')),
  size_bytes     INTEGER NOT NULL,
  sha256         TEXT    NOT NULL UNIQUE,
  source         TEXT    NOT NULL DEFAULT 'upload' CHECK (source IN ('upload', 'paste')),
  encoding       TEXT,                                        -- csv/txt 识别出的编码，如 'gb18030'
  delimiter      TEXT,                                        -- csv 识别出的分隔符
  meta_json      TEXT    NOT NULL,                            -- 见第 4.1 节
  created_at     TEXT    NOT NULL,
  last_used_at   TEXT    NOT NULL
);

-- ============ 任务 ============
CREATE TABLE jobs (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  name                   TEXT    NOT NULL,
  task_type              TEXT    NOT NULL CHECK (task_type IN ('classify', 'summarize')),
  status                 TEXT    NOT NULL
                         CHECK (status IN ('queued', 'running', 'paused', 'completed', 'cancelled')),
  status_reason          TEXT    NOT NULL DEFAULT '',         -- 暂停原因等，给人看的中文
  status_reason_code     TEXT,                                -- 暂停原因码，取值见第 6.1 节；没有原因时为 NULL
  file_id                INTEGER REFERENCES files(id) ON DELETE SET NULL,
  file_name              TEXT    NOT NULL,                    -- 冗余保存，文件记录删除后仍可显示
  source_json            TEXT    NOT NULL,                    -- 数据选择，见第 4.2 节
  prompt_id              INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
  prompt_version         INTEGER NOT NULL,
  prompt_snapshot_json   TEXT    NOT NULL,                    -- 见第 4.3 节
  model_id               INTEGER REFERENCES model_configs(id) ON DELETE SET NULL,
  model_snapshot_json    TEXT    NOT NULL,                    -- 见第 4.3 节，不含密钥
  concurrency            INTEGER NOT NULL CHECK (concurrency BETWEEN 1 AND 20),
  max_retries            INTEGER NOT NULL DEFAULT 2 CHECK (max_retries BETWEEN 0 AND 5),
  dedupe                 INTEGER NOT NULL DEFAULT 1,
  total_items            INTEGER NOT NULL DEFAULT 0,          -- 含跳过的空行
  succeeded_count        INTEGER NOT NULL DEFAULT 0,
  failed_count           INTEGER NOT NULL DEFAULT 0,
  skipped_count          INTEGER NOT NULL DEFAULT 0,
  prompt_tokens          INTEGER NOT NULL DEFAULT 0,
  completion_tokens      INTEGER NOT NULL DEFAULT 0,
  category_colors_json   TEXT    NOT NULL DEFAULT '{}',       -- 意图 → 线路色序号，见第 4.6 节
  category_aliases_json  TEXT    NOT NULL DEFAULT '{}',       -- P1 类别合并：原类别 → 新类别
  created_at             TEXT    NOT NULL,
  started_at             TEXT,                                -- 第一次开始运行的时间
  finished_at            TEXT,                                -- 进入 completed/cancelled 的时间
  updated_at             TEXT    NOT NULL
);
CREATE INDEX idx_jobs_status  ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at DESC);

-- ============ 任务条目 ============
CREATE TABLE job_items (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id             INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  seq                INTEGER NOT NULL,                        -- 任务内顺序，从 1 开始
  row_number         INTEGER NOT NULL,                        -- 原文件行号：Excel 行号或 txt 行号，从 1 开始
  input_text         TEXT    NOT NULL,                        -- 拼接后的完整文本（不截断）
  input_chars        INTEGER NOT NULL,
  row_values_json    TEXT    NOT NULL,                        -- 原始整行 {列 key: 值}，导出用
  dedupe_key         TEXT    NOT NULL,                        -- 去重键，算法见第 4.7 节
  dedup_of           INTEGER REFERENCES job_items(id),        -- 非空：复用这条的结果，引擎不单独请求
  status             TEXT    NOT NULL
                     CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')),
  attempts           INTEGER NOT NULL DEFAULT 0,              -- 已发出的请求次数（含重试）
  model_used         TEXT,                                    -- 实际使用的模型名
  -- 意图识别结果
  label              TEXT,                                    -- 模型输出的类别（规范化后）
  confidence         REAL,                                    -- 0–1，可空
  reason             TEXT,
  -- 摘要结果
  summary            TEXT,
  key_points_json    TEXT,                                    -- [{"text": "...", "sources": [2, 5]}]
  output_chars       INTEGER,                                 -- 摘要（含要点）的字数
  -- 通用
  result_json        TEXT,                                    -- 解析后的完整对象；text 模式为 {"text": "..."}
  raw_output         TEXT,                                    -- 模型原始 content，最长保留 100,000 字
  reasoning          TEXT,                                    -- 思考内容，最长保留 20,000 字
  truncated          INTEGER NOT NULL DEFAULT 0,              -- 1 = 意图识别时截去了中间部分
  omitted_chars      INTEGER,                                 -- 截断时省略的字数；没截断为 NULL
  render_meta_json   TEXT,                                    -- 实际处理时的渲染参数，见第 4.7 节
  chunk_count        INTEGER NOT NULL DEFAULT 1,              -- 摘要分了几段
  error_code         TEXT,                                    -- 见 05 第 6 节
  error_message      TEXT,                                    -- 给人看的中文
  attempt_log_json   TEXT    NOT NULL DEFAULT '[]',           -- 见第 4.5 节，最多保留最近 10 条
  prompt_tokens      INTEGER,
  completion_tokens  INTEGER,
  latency_ms         INTEGER,                                 -- 成功那次请求的耗时；摘要分段时为总耗时
  -- 人工校对（P1，字段第一版就建好）
  manual_label       TEXT,
  reviewed           INTEGER NOT NULL DEFAULT 0,
  note               TEXT,
  started_at         TEXT,
  finished_at        TEXT,
  UNIQUE (job_id, seq)
);
CREATE INDEX idx_items_job_status ON job_items(job_id, status, seq);
CREATE INDEX idx_items_job_label  ON job_items(job_id, label);
CREATE INDEX idx_items_job_dedupe ON job_items(job_id, dedupe_key);
CREATE INDEX idx_items_dedup      ON job_items(dedup_of);
```

后续迁移按编号追加（第 8 节）。`0002_manual_review.sql`（人工复核，01 RES-06、RES-11）给 `job_items` 增加两列：

```sql
-- manual_summary：人工修改后的摘要主旨，NULL 表示没有修改（要点保持模型输出）
-- manual_at：最近一次人工修正（意图或摘要）的时间；没有修正时为 NULL
ALTER TABLE job_items ADD COLUMN manual_summary TEXT;
ALTER TABLE job_items ADD COLUMN manual_at TEXT;
```

人工复核的列：`manual_label`（修正后的意图，只能是任务所用提示词列出的类别，05 第 4.6 节）、`manual_summary`、`manual_at`、`reviewed`、`note`。它们只由人工修改（04 第 8.2 节 PATCH），模型输出的列（`label`、`summary` 等）保持不变，界面据此同时显示修改前后；单条重新处理只重置模型结果，这几列保留；跟随条目同步时不复制这几列。

## 4. JSON 字段结构

### 4.1 `files.meta_json`（FileMeta）

表格类（csv、xlsx、xls）：

```json
{
  "kind": "table",
  "sheets": [
    { "name": "Sheet1", "row_count": 5033, "truncated": false },
    { "name": "Sheet2", "row_count": 12,   "truncated": false }
  ],
  "line_count": null
}
```

- `row_count`：工作表已用区域的总行数，包含表头行。csv 只有一个“工作表”，`name` 固定为 `"CSV"`。
- `truncated`：超过 10 万条数据被截断时为 `true`。

文本类（txt、md、粘贴文本）：

```json
{ "kind": "lines", "sheets": [], "line_count": 1234, "nonempty_line_count": 1200, "truncated": false }
```

### 4.2 `jobs.source_json`（JobSource）

```json
{
  "sheet": "Sheet1",
  "header_row": 1,
  "columns": [
    { "key": "会话ID",   "title": "会话ID",   "letter": "A", "index": 0 },
    { "key": "用户问题", "title": "用户问题", "letter": "B", "index": 1 }
  ],
  "text_columns": ["用户问题"],
  "join_mode": "labeled",
  "start_row": null,
  "limit": 100,
  "split_mode": "line"
}
```

| 字段 | 说明 |
|---|---|
| `sheet` | 表格类为工作表名；文本类为 `null` |
| `header_row` | 表头所在行号，从 1 开始；`0` 表示无表头。文本类固定为 `0` |
| `columns` | 建任务时的全部列，按文件中的顺序。导出时按此顺序输出原始列 |
| `text_columns` | 参与拼接的列 key，按用户选择的顺序。文本类固定为 `["text"]` |
| `join_mode` | 多列拼接方式：`labeled` 每列一行“列标题：值”；`plain` 只取值、用换行连接。单列时两者结果相同，都是值本身 |
| `start_row` | 从原文件哪一行开始取数据；`null` 表示从第一条数据开始 |
| `limit` | 最多取多少条（包含被跳过的空行之外的条目）；`null` 表示全部 |
| `split_mode` | 文本类的切分方式：P0 只有 `line`；P1 增加 `paragraph`、`whole` |

**列 key 规则**：表头单元格非空且在本表内唯一时，key 等于表头文本（去掉首尾空白）；为空时 key 用列字母（`A`、`B`…）；重名时从第二个起加后缀 `(2)`、`(3)`。无表头时 key 一律用列字母。文本类只有一列，key 为 `text`，标题为“文本”。

**limit 的计数方式**：从 `start_row` 起按行读取，空文本行记为 `skipped` 条目但不占 `limit` 名额，直到取满 `limit` 条非空条目或读完。

### 4.3 快照

`prompt_versions.snapshot_json` 与 `jobs.prompt_snapshot_json` 结构相同：

```json
{
  "id": 1, "name": "默认意图识别", "version": 3, "task_type": "classify",
  "system_prompt": "…", "user_template": "…",
  "chunk_template": null, "merge_template": null,
  "output_mode": "json",
  "field_map": { "label": "intent", "confidence": "confidence", "reason": "reason" },
  "temperature": 0.0, "max_output_tokens": 300
}
```

`jobs.model_snapshot_json`：`model_configs` 除密钥、测试结果、时间戳外的全部字段，JSON 字段已解析：

```json
{
  "id": 3, "name": "DeepSeek", "provider_kind": "openai_compatible",
  "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
  "temperature": 0.3, "max_output_tokens": 1024, "max_tokens_param": "max_tokens",
  "context_window": 65536, "timeout_s": 120, "concurrency_cap": 20,
  "json_mode": false, "verify_ssl": true, "proxy_url": null,
  "extra_headers": {}, "extra_body": {}
}
```

快照只用于追溯和展示。任务运行时使用**当前**的模型配置（每次开始或继续运行时读取一次），这样修好密钥后点“继续”即可生效；每条结果的 `model_used` 记录实际用的模型名。

### 4.4 `prompt_templates.field_map_json`

| 任务类型 | 结构 | 内置默认 |
|---|---|---|
| classify | `{"label": 字段名, "confidence": 字段名或 null, "reason": 字段名或 null}` | `{"label": "intent", "confidence": "confidence", "reason": "reason"}` |
| summarize | `{"summary": 字段名, "key_points": 字段名或 null}` | `{"summary": "summary", "key_points": "key_points"}` |

`output_mode = 'text'` 时忽略 field_map。

### 4.5 `job_items.attempt_log_json`

```json
[
  { "at": "2026-10-21T06:05:09.123Z", "attempt": 1, "phase": "request",
    "status_code": 429, "error_code": "RATE_LIMITED",
    "message": "被限流（HTTP 429），2 秒后重试", "latency_ms": 312 },
  { "at": "2026-10-21T06:05:11.551Z", "attempt": 2, "phase": "request",
    "status_code": 200, "error_code": null, "message": "成功", "latency_ms": 820 }
]
```

`phase` 取值：`request`（普通请求）、`parse_repair`（解析失败后的纠正请求）、`chunk 2/5`（摘要第 2 段，共 5 段）、`merge`（合并各段摘要）。

### 4.6 类别颜色与别名

- `category_colors_json`：`{"物流查询": 0, "退款咨询": 1}`。值是线路色序号 0–10，按类别**第一次出现**的顺序分配，分配后不再改变，保证运行中颜色稳定。第 12 个及以后出现的类别值为 `-1`，界面用“其他”灰色（规则见 06 第 3.3 节）。
- `category_aliases_json`（P1）：`{"查物流": "物流查询"}`。

### 4.7 去重键与渲染参数

**`dedupe_key`**：建任务时，按任务的提示词快照把这一行渲染成“普通请求”的完整消息（系统提示词 + 用户消息，05 第 2.4 节；渲染时不截断、不分段），对消息序列化后的文本取 sha1。只比较原文是不够的：模板里可能用了 `{{row_number}}`、`{{col:…}}`、`{{row_json}}`，两行原文相同但其他列不同时，发给模型的内容并不相同，不能共用结果。用了 `{{row_number}}` 的模板，每行的键都不同，去重自然不起作用。

**`render_meta_json`**：条目开始处理时写入，记录当时实际使用的参数，条目详情接口按它重新渲染，保证展示的“发送内容”就是当时发出去的：

```json
{ "today": "2026-10-21", "context_window": 32768, "max_output_tokens": 300, "input_budget": 28940 }
```

`today` 是处理当天的日期（`{{today}}` 用它），`input_budget` 是按 05 第 7.1 节算出的输入预算（截断和分段都以它为准）。

## 5. 设置项

`settings` 表每个 key 一行，`value_json` 存 JSON 值。启动时缺失的 key 按下表补齐。

| key | 默认值 | 取值 |
|---|---|---|
| `default_concurrency.classify` | `5` | 1–20 |
| `default_concurrency.summarize` | `5` | 1–20 |
| `default_limit` | `100` | 正整数，或 `null` 表示全部 |
| `default_max_retries` | `2` | 0–5 |
| `default_dedupe` | `true` | 布尔 |
| `default_model_id.classify` | 演示模型的 id | 模型 id 或 `null` |
| `default_model_id.summarize` | 演示模型的 id | 同上 |
| `default_prompt_id.classify` | 内置意图识别模板的 id | 模板 id |
| `default_prompt_id.summarize` | 内置摘要模板的 id | 模板 id |
| `theme` | `"system"` | `system` / `light` / `dark` |
| `open_mode` | `"app"` | `app`（独立窗口）/ `browser`（默认浏览器） |
| `preferred_port` | `18765` | 1024–65535，重启后生效 |
| `show_demo_model` | `true` | 布尔 |
| `first_close_hint_shown` | `false` | 布尔，托盘提示是否已显示过 |

以下是代码常量，不可设置：

| 常量 | 值 |
|---|---|
| `MAX_CONCURRENCY` | 20 |
| `MAX_ROWS_PER_SOURCE` | 100000 |
| `MAX_UPLOAD_BYTES` | 50 × 1024 × 1024 |
| `RAW_OUTPUT_MAX_CHARS` | 100000 |
| `REASONING_MAX_CHARS` | 20000 |

**默认模型的自动切换**：用户创建第一个非演示模型时，如果两个默认模型设置仍指向演示模型，就把它们都改成这个新模型，并在界面 toast 里说明。

## 6. 状态机

### 6.1 任务

```
创建 ──▶ queued ──引擎接手──▶ running ──条目全部结束──▶ completed
running ──暂停、程序退出、鉴权失败、熔断、写入失败──▶ paused
paused ──继续──▶ running（还有待处理条目）或 completed（已经没有）
paused ──重试失败项──▶ running
completed ──重试失败项、单条重新处理──▶ running
queued、running、paused ──取消──▶ cancelled
```

| 转换 | 触发 | 写入 |
|---|---|---|
| queued → running | 引擎接手 | `started_at`（首次） |
| running → paused | 用户暂停；程序退出；401/403/404；熔断；保存结果失败 | `status_reason`、`status_reason_code` |
| paused → running | 用户继续，且还有待处理的条目 | 清空 `status_reason`、`status_reason_code` |
| paused → completed | 用户继续时已经没有待处理的条目（暂停前派发出去的条目恰好把剩下的做完了） | 清空原因；写 `finished_at` |
| running → completed | 没有 pending、running 条目，且没有暂停或取消请求 | `finished_at` |
| completed → running | 重试失败项；单条重新处理 | 清空 `finished_at` |
| paused → running | 重试失败项（有失败条目时） | 清空原因 |
| queued/running/paused → cancelled | 用户取消 | `finished_at`；未处理的条目保持 `pending` |

**暂停后不自动完成**：暂停时正在处理的条目会继续做完。即使做完后已经没有剩余条目，任务也保持 paused，等用户点“继续”时再按上表转为 completed。这样状态只在用户操作或引擎主动判断时改变，不会在暂停期间悄悄变化。

暂停原因（`status_reason_code` 和对应的 `status_reason` 文案）：

| status_reason_code | 情况 | status_reason |
|---|---|---|
| `user_pause` | 用户暂停 | `已手动暂停` |
| `shutdown` | 程序退出时任务未完成 | `程序退出时任务未完成，可以继续` |
| `auth_failed` | HTTP 401、403 | `模型密钥无效或无权限（HTTP {status}）` |
| `model_not_found` | HTTP 404 | `模型“{model}”不存在，或接口地址不对（HTTP 404）` |
| `circuit_breaker` | 熔断 | `连续 10 条请求失败，最后一次：{错误说明}` |
| `write_failed` | 结果保存失败 | `保存结果失败，请查看日志` |

界面按原因码决定提示和操作（06 第 6.3、6.4 节），不要去匹配中文文案。

### 6.2 条目

```
pending ──派发──▶ running ──成功──▶ succeeded
   ▲                │
   │                ├─ 重试用尽或不可重试 ─▶ failed
   │                │
   └─ 暂停打断、取消、鉴权失败（不计为失败）─┘

failed    ── retry-failed / 单条重新处理 ──▶ pending
succeeded ── 单条重新处理 ──▶ pending
建任务时文本为空 ──▶ skipped（终态，不参与处理）
```

去重的跟随条目（`dedup_of` 非空）不会被派发：主条目结束时，所有跟随条目一次性复制主条目的状态和结果字段（`label`、`confidence`、`reason`、`summary`、`key_points_json`、`output_chars`、`result_json`、`raw_output`、`error_code`、`error_message`），`attempts` 记为 0。单条重新处理一个跟随条目时，先把它的 `dedup_of` 置空，让它成为独立条目。正在处理（running）的条目不能单条重新处理（04 第 8.2 节返回 409）。人工复核的列（第 3 节）属于各条目自己：不随主条目同步，单条重新处理也不清空。

## 7. 派生值

| 值 | 计算 |
|---|---|
| 有效类别 `effective_label` | `manual_label` 非空取它；否则若 `label` 在别名表里取别名；否则取 `label` |
| 有效摘要 | `manual_summary` 非空取它，否则取 `summary` |
| 有效摘要字数 | 摘要修改过时为 `output_chars − 字数(summary) + 字数(manual_summary)`（要点字数不变），否则为 `output_chars` |
| 人工修正 `corrected` | `manual_label` 或 `manual_summary` 非空 |
| `running` 数 | 任务引擎内存中正在处理的条目数（任务不在运行时为 0） |
| `pending` 数 | `total_items − succeeded_count − failed_count − skipped_count − running` |
| 进度百分比 | `(succeeded + failed + skipped) / total_items × 100`，保留 1 位小数 |
| 速度（条/分钟） | 最近 30 条完成（成功或失败）的时间跨度计算；完成不足 5 条时为 `null` |
| 预计剩余秒数 | `(pending + running) / 速度 × 60`；速度为 `null` 时为 `null` |
| 摘要压缩比 | `input_chars / 有效摘要字数`，保留 1 位小数；任务的合计（浓缩计）同样按有效摘要字数 |

计数字段由任务引擎随批量写入同步更新。以下时机按真实数据重算一次，防止漂移：程序启动、任务结束、重试失败项、单条重新处理。

```sql
UPDATE jobs SET
  succeeded_count = (SELECT COUNT(*) FROM job_items WHERE job_id = :id AND status = 'succeeded'),
  failed_count    = (SELECT COUNT(*) FROM job_items WHERE job_id = :id AND status = 'failed'),
  skipped_count   = (SELECT COUNT(*) FROM job_items WHERE job_id = :id AND status = 'skipped')
WHERE id = :id;
```

## 8. 迁移与初始化

- 版本号用 `PRAGMA user_version`。迁移文件放在 `backend/app/db/migrations/`，命名 `NNNN_说明.sql`（四位数字）。
- 启动时按编号顺序执行所有编号大于当前 `user_version` 的文件，每个文件在一个事务中执行，成功后把 `user_version` 设为该编号。
- 迁移失败：记录日志，界面显示“数据库升级失败”，程序不继续启动，也不改动数据。
- 迁移文件随程序打包（见 07）。
- 现有迁移：`0001_init.sql`（初始结构，第 3 节）、`0002_manual_review.sql`（人工复核的两列，第 3 节末尾）。

**启动时的初始化**（每次启动都执行，幂等）：

1. 补齐缺失的设置项（第 5 节）；
2. 按 `builtin_key` 检查两个内置模板，不存在则插入，内容见 05 第 3 节，并写入 `prompt_versions` 的版本 1；
3. 检查演示模型（`provider_kind = 'demo'`），不存在则插入：名称“演示模型”，`base_url = 'demo://local'`，`model = 'wenshu-demo'`，无密钥，`context_window = 32768`；
4. 恢复异常中断的任务：

```sql
UPDATE jobs SET status = 'paused', status_reason = '程序退出时任务未完成，可以继续',
                status_reason_code = 'shutdown', updated_at = :now
 WHERE status IN ('queued', 'running');
UPDATE job_items SET status = 'pending' WHERE status = 'running';
```

5. 对第 4 步涉及的任务按第 7 节重算计数。

## 9. 写入策略

- 引擎不为每条结果单独开事务。所有条目状态变化放进一个异步队列，由单一的写入协程合并提交：每 300 毫秒或攒够 100 条提交一次，同一事务里同时更新 `jobs` 的计数和 tokens。
- 写入协程提交成功后才发布界面事件，保证界面看到的就是已落库的状态。
- 每个写入操作可以附带一个完成通知（`asyncio.Future`），所在事务提交后置位。任务引擎靠它判断一条条目的最终状态何时真正落库，在那之前不会再次派发这条条目（02 第 5.2 节）。
- 读操作（列表、详情、导出）用独立的连接，不等待写入队列。
- 导出和大批量读取使用分页（每次 2,000 行）流式处理，不一次性加载 10 万行。

## 10. 数据目录

```
data/
├── wenshu.db            SQLite（另有 wenshu.db-wal、wenshu.db-shm）
├── secret.key           加密 API Key 用的密钥；删除它会使所有已保存的 API Key 失效
├── uploads/             上传文件：uploads/<sha256 前 2 位>/<sha256>.<扩展名>
├── exports/             导出文件的临时目录，启动时清理 24 小时前的文件
├── logs/                app.log（单个 5 MB，保留 5 个）、selftest.log
├── browser/             独立窗口模式使用的浏览器用户目录
└── runtime.json         运行中进程的端口和 pid，单实例检查用
```

## 11. 容量参考

| 场景 | 估算 |
|---|---|
| 10 万条短文本（平均 50 字）意图识别 | 数据库约 80 MB |
| 1 万条长文本（平均 5,000 字）摘要 | 数据库约 150 MB |

删除任务时级联删除其条目，随后执行 `PRAGMA incremental_vacuum;`。
