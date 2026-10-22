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
