# 文枢后端

FastAPI + SQLAlchemy 2（异步）+ SQLite。提供 `/api/*` 接口、`/api/events` 实时推送、`/mock/v1/*` 演示模型，
并在构建好前端后托管 `app/static` 里的界面。后端可以脱离前端单独运行，接口文档在 `/docs`。

接口和数据结构的依据是 `docs/03-database.md`、`docs/04-api.md`；任务引擎见 `docs/02-architecture.md` 第 5 节。

## 运行要求

- Windows 10 22H2+ / 11（开发和测试在 Linux、macOS 上也能跑，托盘和独立窗口除外）
- Python 3.13

## 创建虚拟环境和安装依赖

在项目根目录的 cmd 里执行：

```bat
"C:\Python313\python.exe" -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
backend\.venv\Scripts\python.exe -c "import fastapi, openai, python_calamine, sqlalchemy; print('ok')"
```

`requirements.txt` 是运行依赖（源码版一键启动只装它），`requirements-dev.txt` 另加测试、检查和打包工具。

## 单独运行后端

```bat
cd backend
set "WENSHU_DATA_DIR=%CD%\..\.devdata"
set "WENSHU_PORT=18765"
set "WENSHU_DEV=1"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18765 --reload --reload-dir app
```

- 接口文档：<http://127.0.0.1:18765/docs>（Swagger UI，始终开启）。不从 CDN 加载：脚本和样式随后端分发在
  `app/vendor/swagger-ui/`（swagger-ui-dist 5.x，见其中的 `VERSION`），由后端以 `/docs-assets/` 提供，断网也能打开；
- 健康检查：<http://127.0.0.1:18765/api/health>
- `app/static` 不存在时（前端还没构建），访问 `/` 返回纯文字说明“前端尚未构建……”，接口不受影响。

`scripts\dev.bat` 会同时启动后端（热更新）和前端开发服务器，平时开发用它即可。

注意：除 GET、OPTIONS 外的 `/api` 请求必须带请求头 `X-WenShu-Client: 1`，`Host` 必须是 `127.0.0.1:{端口}` 或
`localhost:{端口}`。在 `/docs` 里调用非 GET 接口时，先点右上角 **Authorize**，填 `1`（刷新页面后仍然记得）；用 curl 时加
`-H "X-WenShu-Client: 1"`。

## 环境变量

| 变量 | 作用 |
|---|---|
| `WENSHU_DATA_DIR` | 数据目录。不设置时依次取 `backend\data`（可写时）、`%LOCALAPPDATA%\WenShu\data`；`启动文枢.bat` 设为项目根目录的 `data`，`dev.bat` 设为 `.devdata` |
| `WENSHU_PORT` | 后端自己的端口（引擎调用演示模型时拼地址用）；启动器、`dev.bat` 会传入。直接用 uvicorn 换端口时，后端会从第一个请求里自动更正 |
| `WENSHU_DEV` | `1`：开发模式，日志级别 DEBUG，注册 `POST /api/_dev/reset`（清空数据、重跑初始化，测试用），`/api/system/shutdown` 只暂停任务、不退出进程 |
| `WENSHU_MOCK_FAIL_RATE` | 演示模型的随机故障率，默认 `0.02`；自动化测试里为 `0` |
| `WENSHU_LOG_LEVEL` | 覆盖日志级别；只有显式设为 `DEBUG` 时才记录消息内容的前 200 字 |
| `WENSHU_CORS_ORIGINS` | 前端单独部署时放行的来源，逗号分隔，如 `http://127.0.0.1:4173`；不设置则不返回任何 CORS 头 |
| `WENSHU_MODELS_FILE` | “默认自定义模型”的本机配置文件路径，默认 `backend\models.local.json`（打包版为 exe 同目录的 `models.local.json`），见下文 |

## 首次启动的默认数据

每次启动都会执行初始化（幂等，`app/db/seed.py`）：

1. 补齐缺失的设置项（`docs/03-database.md` 第 5 节）；
2. 两套内置提示词“默认意图识别”“默认文本摘要”（内容见 `app/services/defaults.py`，与 `docs/05` 第 3 节一致）；
3. 演示模型（`demo://local`，不需要密钥、不联网）；
4. **默认自定义模型**：
   - 如果存在本机配置文件 `models.local.json`（或 `WENSHU_MODELS_FILE` 指向的文件），按名称导入其中的模型（一个对象或对象数组，字段同接口的 `ModelConfigInput`：`name`、`base_url`、`api_key`、`model`，以及可选的 `temperature`、`max_output_tokens`、`context_window`、`concurrency_cap`、`json_mode`、`extra_headers`、`extra_body` 等）。库里已有同名模型时不覆盖，之后以界面里的修改为准；密钥加密后入库；
   - 没有配置文件且是第一次建库时，生成一条**已停用的占位条目**“自定义模型”（地址 `https://api.example.com/v1`、模型名 `your-model-name`、无密钥）。在模型页编辑它、填入真实的地址和密钥后会自动启用；
   - 第一个真实模型出现时，如果两种任务的默认模型仍是演示模型，自动改为这个模型。
   - 示例见 `backend/models.local.json.example`。`models.local.json` 含明文密钥，已在 `.gitignore` 里忽略；它不在 `data` 目录里，所以“data 目录里搜不到密钥”的检查不受影响。
5. 恢复异常中断的任务：`queued`、`running` 改为 `paused`（原因码 `shutdown`，原因“程序退出时任务未完成，可以继续”），`running` 的条目放回 `pending`，并重算计数。

暂停原因码（`status_reason_code`，界面按它决定提示和操作）：`user_pause`、`shutdown`、`auth_failed`、`model_not_found`、
`circuit_breaker`、`write_failed`，文案见 `app/services/job_engine/reasons.py`（`docs/03-database.md` 第 6.1 节）。

## 数据库位置与迁移

- 数据库是数据目录下的 `wenshu.db`（WAL 模式），API Key 用 `secret.key` 加密（删除它会使已保存的密钥失效）；
- 迁移文件在 `app/db/migrations/`，命名 `NNNN_说明.sql`，用 `PRAGMA user_version` 记录版本，启动时按编号执行所有更新的文件，每个文件一个事务；
- 迁移失败会写日志（`data/logs/app.log`）并停止启动，不改动数据；
- 新增表或字段：新建下一个编号的迁移文件，同时更新 `app/db/models.py` 和 `docs/03-database.md`；
- 新库文件的第一个连接先设 `auto_vacuum = INCREMENTAL` 再切 WAL，启动时检查它是否为 2，不是则记警告；
- **审核版文档改了 `0001_init.sql`**（`jobs.status_reason_code`；`job_items.text_hash` 改名 `dedupe_key`，新增
  `omitted_chars`、`render_meta_json`）。1.0.0 还没发布，没有另加迁移：用审核前的代码建过的开发数据库
  （`.devdata\`、`data\`、`.e2edata\`）请删除后重建；
- `0002_manual_review.sql`：人工复核给 `job_items` 加了 `manual_summary`、`manual_at` 两列。已有的数据库启动时自动升级，
  不用删库。

数据目录结构：

```
data/
├── wenshu.db、wenshu.db-wal、wenshu.db-shm
├── secret.key        加密 API Key 用的密钥
├── uploads/          上传文件：uploads/<sha256 前 2 位>/<sha256>.<扩展名>
├── exports/          导出文件的临时目录，启动时清理 24 小时前的文件
├── logs/             app.log（单个 5 MB，保留 5 个）、selftest.log
├── browser/          独立窗口模式使用的浏览器用户目录
└── runtime.json      运行中进程的端口和 pid（单实例检查用）
```

## 演示模型

挂在 `/mock/v1`（`POST /mock/v1/chat/completions`、`GET /mock/v1/models`），兼容 Chat Completions 的常用子集，支持流式。
任务引擎调用它时和调用真实模型走完全相同的 HTTP 路径（`http://127.0.0.1:{端口}/mock/v1`）。

- 意图识别：从 system 消息里 `- 类别名：说明` 形式的行提取类别，user 消息里出现了哪个类别名就选它，否则按文本哈希选；
- 文本摘要：取 `[n] 内容` 形式的段落，生成“演示摘要：……”和带段落编号的要点；合并请求时合并各部分要点；
- 合并请求的判定：最后一条 user 消息里有一行恰好是“第 1 部分：”（正则 `(?m)^第 1 部分：$`）；分段模板第 1 段不会被误判；
- 延迟：意图识别 300–1200 毫秒，摘要 800–2500 毫秒；
- 随机故障（`WENSHU_MOCK_FAIL_RATE`）只注入非流式的意图识别、摘要请求；试运行（流式）和测试连接（回显）从不注入。

请求头 `X-Mock-Behavior`（逗号分隔多个；接入模型时写在“自定义请求头”里即可）：

| 值 | 效果 |
|---|---|
| `none` | 关闭随机故障 |
| `rate_limit` / `rate_limit_first` | 总是 / 同样内容的请求第一次返回 429（`Retry-After: 1`） |
| `server_error` / `server_error_first` | 总是 / 同样内容的请求第一次返回 500 |
| `timeout` | 挂起 600 秒不返回 |
| `auth` | 返回 401 |
| `not_found` | 返回 404 |
| `context` | 返回 400，“This model's maximum context length is 8192 tokens” |
| `bad_json` | 返回不是 JSON 的文字 |
| `think` | 在内容前加 `<think>演示思考过程……</think>` |
| `reasoning_field` | 把演示思考内容放在 `reasoning_content` 字段 |
| `truncate` | 内容截掉后一半，`finish_reason = "length"` |
| `empty` | 返回空内容 |
| `slow` / `fast` | 延迟乘以 5 / 改为 0–5 毫秒 |

“同样内容”按请求里的 `model` + 全部消息内容的 sha1 判断，记录在演示模型进程内。

验收辅助（`docs/04-api.md` 第 11 节，不进 OpenAPI）：

- `GET /mock/v1/_stats`：`{"inflight": 3, "max_inflight": 8, "total": 1042, "by_status": {"200": 1030, "429": 12}}`，
  `max_inflight` 是上次重置以来同时处理的最大请求数；
- `POST /mock/v1/_reset`：清零统计，并清空“首次请求”的记录，返回 204。

例如验证“同时请求数不超过 8”：先 `curl -X POST http://127.0.0.1:18765/mock/v1/_reset`，跑完任务后再
`curl http://127.0.0.1:18765/mock/v1/_stats` 看 `max_inflight`。内置演示模型不允许改请求头，需要 `X-Mock-Behavior` 时，
新建一个地址为 `http://127.0.0.1:18765/mock/v1`、带这个请求头的模型。

## 测试与代码检查

在项目根目录执行：

```bat
backend\.venv\Scripts\python.exe -m pytest backend\tests
backend\.venv\Scripts\python.exe -m ruff check backend
```

- 开发依赖装 `requirements-dev.txt`（pytest、pytest-asyncio、xlwt 等）。`启动文枢.bat` 建的虚拟环境只装了运行依赖，
  直接跑测试会报 “async def functions are not natively supported”、生成 `legacy.xls` 时缺 xlwt；
- 开着系统代理时，先 `set NO_PROXY=127.0.0.1,localhost` 再跑测试。测试和后端的 HTTP 客户端都设了 `trust_env=False`，
  不读代理设置，这一步是保险；

- 测试基础设施（`docs/02-architecture.md` 第 11.1 节，`tests/conftest.py`）：会话级的真实服务在后台线程里运行
  （先绑定 `127.0.0.1:0` 拿空闲端口，临时数据目录，`WENSHU_DEV=1`、`WENSHU_MOCK_FAIL_RATE=0`），引擎通过 HTTP 调用演示模型；
  每个用例开始前调用 `POST /api/_dev/reset` 和 `POST /mock/v1/_reset`，用例之间互不影响；`client` fixture 是
  `httpx.AsyncClient`，`api` 是带辅助方法的同步客户端；
- 测试数据在项目根目录的 `testdata/`（不提交），缺文件时测试会先运行 `scripts/make_testdata.py` 生成；生成脚本改过时
  （`testdata/.make_testdata.sha256` 记录的脚本哈希对不上）全部重新生成，不会继续用旧数据。也可以手动生成，
  再拿这些文件去界面里验收：`backend\.venv\Scripts\python.exe scripts\make_testdata.py`（`--force` 全部重建）；不需要网络和 API Key；
- 测试里写文本文件一律 `newline=""`：Windows 的文本模式会把 `\n` 换成 `\r\n`，写进去的 `\r\n` 会变成 `\r\r\n`；
- Ruff 的 import 排序等可自动修复的问题：`backend\.venv\Scripts\python.exe -m ruff check backend --fix`。

## 目录说明

```
backend/
├── app/
│   ├── __init__.py          APP_NAME、APP_ID、__version__（版本号的唯一来源）
│   ├── main.py              create_app()、生命周期；模块级 app 供 uvicorn 使用
│   ├── config.py            路径、环境变量、常量、日志
│   ├── security.py          Host 检查、X-WenShu-Client 检查、上传大小预检
│   ├── context.py           生命周期里创建的共享对象（数据库、引擎、事件总线……）
│   ├── utils.py             时间格式、JSON
│   ├── db/                  异步引擎、ORM 模型、迁移、初始化、repo（按表组织的读写函数）
│   ├── schemas/             Pydantic 模型，字段与 docs/04 一一对应
│   ├── api/                 薄路由层（system、settings、models、prompts、playground、files、jobs、items、export、events、mock、static）
│   ├── services/            业务逻辑：模型调用、提示词渲染、输出解析、长文本切分、文件解析、建任务、任务引擎、导出……
│   │   └── job_engine/      JobManager、JobRunner、并发闸门、单条处理器、写入协程、进度
│   ├── launcher/            启动器：单实例、端口、打开界面、托盘、自检（源码版和打包版共用，只用绝对导入）
│   ├── vendor/swagger-ui/   /docs 用的 Swagger UI 静态文件（提交）
│   └── static/              前端构建产物（scripts\build-web.bat 复制进来，不提交）
├── tests/                   pytest 用例；测试数据由根目录的 scripts/make_testdata.py 生成到 testdata/
├── models.local.json.example
├── requirements.txt、requirements-dev.txt
└── pyproject.toml           Ruff、pytest 配置
```
