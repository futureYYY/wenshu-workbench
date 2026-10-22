# 02 技术架构

> 文枢开发文档 · 第 2 篇。本文规定技术选型、代码组织和几个核心机制的实现方式。

## 1. 总体架构

正式运行时只有一个进程：

```
┌──────────────────────────────── WenShu.exe ─────────────────────────────────┐
│                                                                             │
│  启动器（主线程）                                                             │
│   单实例检查 → 选端口 → 启动后端线程 → 等待健康检查 → 打开界面 → 托盘图标常驻      │
│                                                                             │
│  后端线程：Uvicorn + FastAPI（asyncio 事件循环）                                │
│   ├─ /api/*            REST 接口                                             │
│   ├─ /api/events       SSE 实时推送                                           │
│   ├─ /mock/v1/*        演示模型（OpenAI 兼容）                                 │
│   └─ /*                前端静态文件（Vue 构建产物，未知路径回退 index.html）       │
│                                                                             │
│   服务层   文件解析  提示词渲染  模型调用  输出解析  长文本处理  导出               │
│   任务引擎 JobManager → JobRunner（每个运行中的任务一个）→ 任务级、模型级并发闸门    │
│   事件总线 EventBus → SSE                                                     │
│   持久化   SQLAlchemy 2（异步）+ aiosqlite → data/wenshu.db（WAL）              │
└─────────────────────────────────────────────────────────────────────────────┘
        │ HTTPS：POST {base_url}/chat/completions
        ▼
  云端模型 API ／ 公司内网模型网关 ／ 本机 Ollama、vLLM ／ 内置演示模型

  界面：Edge 或 Chrome 的应用模式窗口（--app），或默认浏览器，访问 http://127.0.0.1:{端口}
```

上图是打包版的样子。项目一共有三种运行方式。前两种是给使用者的一键启动，运行的是同一套启动器代码（`app/launcher`），行为完全一致：

| 方式 | 怎么启动 | 进程 | 界面从哪来 | 默认数据目录 |
|---|---|---|---|---|
| 打包版 | 双击 `release\WenShu\WenShu.exe` | 一个：exe | exe 内置的前端构建产物 | `release\WenShu\data` |
| 源码版 | 双击项目根目录的 `启动文枢.bat` | 一个：`pythonw.exe -m app.launcher` | `backend/app/static`，首次和前端源码变化后自动构建 | 项目根目录的 `data` |
| 开发 | `scripts\dev.bat` | 两个：`uvicorn --reload`（18765）和 Vite 开发服务器（5173，热更新，把 `/api`、`/mock`、`/docs`、`/openapi.json` 代理到后端） | Vite | 项目根目录的 `.devdata` |

三种方式默认使用不同的数据目录，互不干扰。想让源码版和打包版共用数据，在 `scripts\local.env.cmd` 里设置 `WENSHU_DATA_DIR`（07 第 5.5 节）。

### 1.1 前后端分离的约定

1. `frontend/` 和 `backend/` 是两个独立工程：各自有依赖清单（`package.json`、`requirements.txt`）、README、启动命令和测试，都能单独运行。
2. 两者之间唯一的契约是 04 定义的 HTTP 接口和 SSE 事件。前端类型从后端的 OpenAPI 生成；前端不读取后端的任何文件，后端不引用前端代码。
3. 前端的接口地址由构建变量 `VITE_API_BASE` 决定，默认为空（同源）。前端单独部署时把它设为后端地址（如 `http://127.0.0.1:18765`），并在后端用环境变量 `WENSHU_CORS_ORIGINS` 放行前端所在的来源（第 10 节）。
4. 后端托管前端静态文件只是一种部署方式。`backend/app/static` 不存在时，后端照常提供全部接口，`GET /` 返回一个纯文字说明页：“前端尚未构建。运行 scripts\build-web.bat 构建，或用 scripts\dev.bat 开发。”

## 2. 技术栈与版本

版本核对于 2026-10-21。约束写法：`~=X.Y.Z` 表示允许 X.Y 内的补丁更新；`^` 为 npm 的兼容范围。安装时如有更新的补丁版本可以直接用；**跨主版本升级必须先改本文档**。

### 2.1 运行环境

| 项 | 版本 | 说明 |
|---|---|---|
| Windows | 10 22H2 及以上、11，x64 | |
| Python | 3.13（本机 Miniconda 自带 3.13.9） | 在项目内建 venv，见 07 第 2.1 节 |
| Node.js | 24（本机 24.12.0） | Vite 8 要求 ≥ 22.12 |
| 浏览器 | Edge 或 Chrome 新版 | 独立窗口用 `--app` 应用模式 |

### 2.2 后端依赖

`backend/requirements.txt`：

```text
fastapi~=0.156.8
uvicorn~=0.54.0
sqlalchemy[asyncio]~=2.1.5
aiosqlite~=0.22.1
pydantic>=2.14.1,<3
python-multipart~=0.0.32
sse-starlette>=3.5.0,<4
openai>=3.35.1,<4
python-calamine~=0.9.0
openpyxl~=3.1.5
charset-normalizer>=3.5.2,<4
cryptography>=50.0.2,<51
json-repair~=0.64.1
pystray==0.19.5
pillow>=13.0.0,<14
```

`backend/requirements-dev.txt`：

```text
-r requirements.txt
pytest>=9.1.1,<10
pytest-asyncio>=1.4.0,<2
httpx~=0.28.1
ruff~=0.17.1
pyinstaller>=6.22.3,<7
xlwt==1.3.0
```

| 包 | 用途 | 需要注意 |
|---|---|---|
| fastapi、uvicorn | Web 框架和服务器 | FastAPI 仍是 0.x，次版本之间可能有破坏性变化，所以锁定在 0.156 |
| sqlalchemy[asyncio]、aiosqlite | 异步 ORM 和 SQLite 驱动 | SQLAlchemy 2.1 不再自动安装 greenlet，必须带 `[asyncio]` |
| sse-starlette | SSE 响应 | |
| openai | 调用 OpenAI 兼容接口 | 3.x 默认的 HTTP 客户端是 `httpx2`（httpx 的后续版本），不再安装 httpx；证书默认使用系统证书库。用法见 05 第 1.1 节 |
| python-calamine | 读取 xlsx、xls | 支持 `iter_rows()` 流式读取 |
| openpyxl | 写出 xlsx | |
| charset-normalizer | 识别 csv、txt 编码 | |
| cryptography | API Key 加密（Fernet） | |
| json-repair | 修复残缺的 JSON 输出 | |
| pystray、pillow | 托盘图标 | pystray 最后一次发布是 2023 年，在 Windows 上用 ctypes 实现，Python 3.13 可用。阶段 6 若遇到兼容问题，改用 pywin32 自行实现托盘，接口保持 `tray.py` 不变 |
| httpx | 测试里作为客户端，请求测试启动的真实服务（第 11 节） | 只在开发依赖里 |
| pyinstaller | 打包 | 6.22 支持 Python 3.13 |
| xlwt | 生成 xls 测试文件 | 只在开发依赖里 |

P1 做 docx、pdf 时再加：`python-docx~=1.2.0`、`pypdf>=6.21.1,<7`。

**Swagger UI 静态文件**：`/docs` 不从 CDN 加载（04 第 12 节）。从 npm 包 `swagger-ui-dist`（5.x 的最新版）里取 `swagger-ui-bundle.js`、`swagger-ui.css` 和它的 LICENSE，提交到 `backend/app/vendor/swagger-ui/`，由后端以 `/docs-assets/` 路径提供。只在阶段 0 取一次，例如在任意临时目录执行 `npm pack swagger-ui-dist` 后解压；后端运行时不依赖 Node。

### 2.3 前端依赖

`frontend/package.json` 的依赖：

| 包 | 版本 | 类别 | 需要注意 |
|---|---|---|---|
| vue | ^3.5.44 | 运行 | 3.6 尚未正式发布，不要用 |
| vue-router | ^5.4.0 | 运行 | 手写路由表，不用文件路由 |
| pinia | ^4.1.0 | 运行 | 只提供 ESM |
| reka-ui | ^2.11.0 | 运行 | |
| @vueuse/core | ^15.0.0 | 运行 | |
| motion-v | ^2.8.0 | 运行 | Motion 官方的 Vue 版本 |
| @tanstack/vue-table | ^8.21.0 | 运行 | **用 v8**。v9 重写了 API，网上的示例和多数模型熟悉的都是 v8；本项目只用到列定义、列宽和排序状态 |
| @tanstack/vue-virtual | ^3.13.47 | 运行 | |
| codemirror | ^6.0.2 | 运行 | 连同 `@codemirror/view`、`@codemirror/state`（与之配套的最新版） |
| @codemirror/lang-markdown | ^6.5.2 | 运行 | |
| @codemirror/autocomplete | ^6.20.4 | 运行 | |
| vue-sonner | ^2.0.9 | 运行 | |
| markdown-it | ^15.0.3 | 运行 | v15 去掉了 `lib/*` 子路径，只从包入口导入 |
| dompurify | ^3.4.17 | 运行 | |
| @lucide/vue | ^1.61.0 | 运行 | `lucide-vue-next` 已废弃，不要用 |
| openapi-fetch | ^0.17.0 | 运行 | |
| @fontsource-variable/noto-sans-sc | ^5.3.1 | 运行 | 界面字体，OFL 许可 |
| @fontsource-variable/overpass | ^5.3.0 | 运行 | 导视数字，OFL 许可 |
| @fontsource/overpass-mono | ^5.3.0 | 运行 | 等宽字体，OFL 许可 |
| vite | ^8.3.5 | 开发 | 基于 Rolldown；不要用 `build.rollupOptions` 的对象式 `manualChunks`，保持默认分包 |
| @vitejs/plugin-vue | ^6.0.10 | 开发 | |
| typescript | ~6.0.3 | 开发 | **不要升级到 7**：TypeScript 7 没有 JS API，vue-tsc 无法使用 |
| vue-tsc | ^3.3.13 | 开发 | |
| tailwindcss、@tailwindcss/vite | ^4.3.3 | 开发 | |
| vitest | ^5.0.5 | 开发 | 配 `jsdom` |
| @vue/test-utils | ^2.5.1 | 开发 | |
| @playwright/test | 1.64.1 | 开发 | 与本机已装的 Playwright 一致 |
| eslint | ^10.13.0 | 开发 | 配 `eslint-plugin-vue`、`typescript-eslint`、`prettier`，取与 ESLint 10、TypeScript 6 兼容的最新版 |

`openapi-typescript`（7.13.0）的对等依赖要求 TypeScript 5，与本项目的 TypeScript 6 冲突，所以**不装进项目**，用 `npx` 临时运行（第 8.2 节）。

## 3. 目录结构

```
wenshu/
├── AGENTS.md
├── README.md                      项目说明（内容见 08 第 8 节）
├── 启动文枢.bat                    源码版一键启动（07 第 5.5 节）
├── .gitignore
├── docs/
├── scripts/
│   ├── dev.bat                    开发：同时启动后端和前端（热更新）
│   ├── setup.bat                  源码版首次使用：创建后端虚拟环境并安装依赖
│   ├── prestart.py                源码版启动前检查：依赖和前端构建是否最新（只用标准库）
│   ├── build-web.bat              构建前端并复制到 backend\app\static
│   ├── build.bat                  打包：测试 → 构建前端 → PyInstaller → 自检 → 压缩 → 同步到 release
│   ├── make_testdata.py           生成测试数据到 testdata/（后端测试和端到端测试共用）
│   └── local.env.cmd.example      本机配置示例（Python 路径、数据目录），复制为 local.env.cmd 使用
├── testdata/                      测试数据（make_testdata.py 生成，不提交）
├── packaging/
│   ├── wenshu.spec                PyInstaller 配置
│   ├── wenshu_main.py             PyInstaller 入口：只做 from app.launcher.entry import main; main()
│   ├── make_icon.py               生成 icon.ico
│   ├── make_version_info.py       生成 version_info.txt
│   ├── icon.ico                   exe 和托盘图标（16–256 px）
│   ├── icon.svg                   图标源文件
│   └── version_info.txt           exe 文件属性里的版本信息（生成，不提交）
├── release/                       打包产物（不提交）
├── build/                         打包中间产物（不提交）
├── data/                          源码版的数据（不提交）
├── .devdata/                      开发模式的数据（不提交）
├── .e2edata/                      端到端测试的数据（不提交）
├── backend/
│   ├── README.md                  后端说明：单独运行、测试、环境变量
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pyproject.toml             Ruff、pytest 配置
│   ├── app/
│   │   ├── __init__.py            APP_NAME = "文枢"、APP_ID = "WenShu"、__version__
│   │   ├── main.py                create_app()、生命周期
│   │   ├── config.py              路径、环境变量、常量
│   │   ├── security.py            Host 检查、X-WenShu-Client 检查中间件
│   │   ├── db/
│   │   │   ├── engine.py          异步引擎、连接设置
│   │   │   ├── models.py          SQLAlchemy 模型（与 03 第 3 节一一对应）
│   │   │   ├── migrate.py         迁移执行器
│   │   │   ├── migrations/        0001_init.sql、0002_manual_review.sql ……
│   │   │   ├── seed.py            启动初始化（03 第 8 节）
│   │   │   └── repo/              按表组织的读写函数
│   │   ├── schemas/               Pydantic 模型（与 04 一一对应）
│   │   ├── api/
│   │   │   ├── errors.py          AppError、统一错误处理
│   │   │   ├── system.py  settings.py  models.py  prompts.py  playground.py
│   │   │   ├── files.py  jobs.py  items.py  export.py  events.py
│   │   │   ├── mock.py            演示模型
│   │   │   └── static.py          静态文件和 SPA 回退
│   │   ├── services/
│   │   │   ├── crypto.py          API Key 加解密、掩码
│   │   │   ├── llm_client.py      客户端缓存、请求构造、错误分类
│   │   │   ├── prompt_render.py   变量渲染、消息组装
│   │   │   ├── output_parser.py   JSON 提取、字段映射、类别规范化、思考剥离
│   │   │   ├── segmenter.py       token 估算、段落切分、截断、分段
│   │   │   ├── file_parser/       detect.py  csv_parser.py  excel_parser.py  text_parser.py
│   │   │   ├── job_builder.py     从文件生成条目、预估
│   │   │   ├── job_engine/        manager.py  runner.py  limiter.py  processor.py  writer.py  progress.py
│   │   │   ├── event_bus.py
│   │   │   ├── exporter.py
│   │   │   ├── review.py          人工复核：修正意图、修改摘要的校验和有效值（05 第 4.6 节）
│   │   │   └── defaults.py        内置提示词、默认设置
│   │   ├── launcher/
│   │   │   ├── __main__.py        源码版入口：python -m app.launcher
│   │   │   ├── entry.py           启动流程（打包版和源码版共用）
│   │   │   ├── single_instance.py
│   │   │   ├── ports.py
│   │   │   ├── browser.py         查找 Edge、Chrome，打开应用窗口
│   │   │   ├── tray.py
│   │   │   └── selftest.py
│   │   ├── vendor/swagger-ui/     /docs 用的 Swagger UI 静态文件（第 2.2 节，提交）
│   │   └── static/                前端构建产物（build-web.bat 复制进来，不提交）
│   └── tests/
│       ├── conftest.py            起真实服务、临时数据目录、测试客户端（第 11 节）
│       └── test_*.py
└── frontend/
    ├── README.md                  前端说明：开发、构建、单独部署
    ├── .env.example               VITE_API_BASE 示例
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html                 含主题防闪烁脚本
    ├── playwright.config.ts
    ├── e2e/                       端到端测试
    └── src/
        ├── main.ts
        ├── App.vue                外壳：导航栏、页面栏、全局浮层
        ├── router/index.ts
        ├── api/
        │   ├── schema.d.ts        openapi-typescript 生成，不要手改
        │   ├── client.ts          openapi-fetch 客户端、统一错误处理
        │   ├── events.ts          SSE 订阅
        │   └── stream.ts          试运行的 POST 流读取
        ├── stores/                settings.ts  models.ts  prompts.ts  jobs.ts  files.ts  ui.ts
        ├── composables/           useJobLive.ts  useGlobalEvents.ts  useShortcuts.ts  useDraft.ts
        ├── design/
        │   ├── tokens.css         设计令牌（06 第 3 节）
        │   ├── fonts.css
        │   ├── base.css           Tailwind 入口、基础排版
        │   ├── palette.ts         线路色分配和对比度规则
        │   └── motion.ts          动效常量、减少动态效果判断
        ├── components/
        │   ├── base/              Button、Input、Select、Slider、Drawer、Toast …
        │   ├── metro/             LineBadge、StationDot、MetroStepper、LineProgress、
        │   │                      LineMap、ParallelTracks、ExpressTrace、CompressionGauge
        │   ├── data/              DataGrid、PreviewGrid
        │   └── editor/            PromptEditor、JsonView
        ├── features/
        │   ├── home/  new-job/  jobs/  job-detail/  reading/
        │   ├── prompts/  models/  settings/
        │   └── command-palette/  drop-overlay/  dev-components/
        ├── types/                 第三方包的类型声明（lucide-vue.d.ts，见 frontend/README.md）
        └── utils/                 format.ts  text.ts  keyboard.ts
```

## 4. 后端模块职责

| 模块 | 职责 |
|---|---|
| `main.py` | `create_app()` 组装应用：注册中间件、路由、错误处理、静态文件。生命周期启动时：执行迁移、初始化数据（03 第 8 节）、启动写入协程和 JobManager；关闭时：暂停全部任务（第 5.7 节）、关闭模型客户端 |
| `config.py` | 解析路径（第 9 节）、读取环境变量、定义 03 第 5 节的常量 |
| `security.py` | 第 10 节的两项请求检查 |
| `db/` | 只有这里写 SQL 或 ORM 查询；其他模块调用 `repo` 里的函数 |
| `schemas/` | 请求和响应模型，字段与 04 完全一致；`_json` 字段在这里解析成对象 |
| `api/` | 薄路由层：校验、调用服务、返回模型。不写业务逻辑 |
| `services/` | 业务逻辑，尽量写成可单独测试的纯函数（渲染、解析、切分、导出都是） |
| `launcher/` | 打包版和源码版共用的启动器；开发模式（`dev.bat`）不经过它。资源路径按第 9.1 节区分两种运行方式，不要无条件使用 `sys._MEIPASS`。只用绝对导入（`from app.launcher import …`），因为打包入口不在包内（07 第 6 节） |

## 5. 任务引擎

### 5.1 组成

| 组件 | 职责 |
|---|---|
| `JobManager` | 全局唯一。每个任务最多持有一个 `JobRunner`（执行器）；提供开始、暂停、继续、取消、重试失败项、单条重跑；程序退出时暂停全部 |
| `JobRunner` | 每个运行中（或暂停后还在收尾）的任务一个，跑在一个 asyncio 任务里；按顺序取待处理条目并派发 |
| `ResizableLimiter` | 容量可在运行中调整的并发闸门；任务级和模型级各用一个 |
| `ModelLimiters` | 按模型 id 管理模型级闸门，容量为该模型的 `concurrency_cap`，配置修改后调整容量 |
| `ItemProcessor` | 处理一条：渲染、长文本处理、请求、重试、解析 |
| `ResultWriter` | 唯一的写入协程，合并提交（03 第 9 节） |
| `ProgressTracker` | 每个任务一个：进行中集合、最近完成时间、速度、剩余时间 |
| `EventBus` | 进程内发布订阅，供 SSE 使用 |

### 5.2 并发控制

两级闸门：每条条目先拿**任务级**名额（容量 = 任务并发），每次发 HTTP 请求前再拿**模型级**名额（容量 = 模型并发上限），请求结束立即归还模型级名额。等待重试期间只归还模型级名额，保留任务级名额。

```python
class ResizableLimiter:
    """容量可在运行中调整的信号量。"""
    def __init__(self, capacity: int) -> None: ...
    async def acquire(self) -> None: ...       # 等到 in_use < capacity
    def release(self) -> None: ...
    def resize(self, capacity: int) -> None:   # 调大立即唤醒等待者；调小不打断进行中的，只限制之后的获取
        ...
```

`JobRunner` 的主循环：

```python
async def run(self) -> None:
    async with asyncio.TaskGroup() as tg:
        while True:
            if self.stop_requested:                         # 暂停或取消：不再派发，等进行中的条目收尾
                if not self.in_flight:
                    break
                await self._wait_wake()                     # 条目落库、或“继续”清除了停止请求时被唤醒
                continue
            batch = await repo.pending_leaders(             # 只取主条目（dedup_of 为空）且 status = 'pending'
                self.job_id, after_seq=self.cursor,         # 键集分页：seq > cursor，按 seq 升序
                exclude_ids=self.in_flight, limit=500)      # 排除已派发、结果还没落库的
            if not batch:
                if self.cursor > 0:                         # 扫到底了，从头再扫一遍，捡回运行中被单条重跑的条目
                    self.cursor = 0
                    continue
                if not self.in_flight:                      # 从头扫也没有，进行中的也都落库了：全部完成
                    break
                await self._wait_wake()
                continue
            for item in batch:
                while len(self.in_flight) >= MAX_UNCOMMITTED and not self.stop_requested:
                    await self._wait_wake()                 # 背压：等写入协程赶上来
                if self.stop_requested:
                    break
                await self.job_slots.acquire()
                if self.stop_requested:
                    self.job_slots.release()
                    break
                self.cursor = item.seq
                self.in_flight.add(item.id)
                tg.create_task(self._process(item))
    await self._finish()
```

要点：

- **分页**：用 `seq > cursor` 的键集分页，每次取 500 条，避免一次性把 10 万条读进内存。不要用 OFFSET，也不要每次从头重查 pending：已派发的条目在写入协程提交前（最长 300 毫秒）数据库里仍是 pending，会被重复派发。
- **`in_flight`**：从派发开始，到这条的最终状态被写入协程提交为止（03 第 9 节的完成通知）。查询时排除它们。
- **`_process` 不抛异常**：内部捕获全部异常，只让 `asyncio.CancelledError` 继续抛出。`TaskGroup` 只要有一个子任务抛异常，就会取消其他所有子任务，`_finish()` 也不会执行。需要暂停整个任务时（鉴权失败、模型不存在、熔断、写入失败），调用 `self.request_stop("pause", 原因码, 原因)`，不要用抛异常的方式。被取消的子任务不会触发连带取消。
- **名额与唤醒**：`_process` 处理结束就释放任务级名额，不等落库；等完成通知置位后，再把条目移出 `in_flight` 并唤醒主循环。被取消时（取消任务、程序退出），先把“放回 pending”交给写入协程，然后在 `finally` 里直接移出 `in_flight`、释放名额、唤醒主循环，不等完成通知，否则主循环会一直等下去。
- **`_finish()`**：只在 `stop_requested` 为空时把任务置为 completed；暂停、取消时不改状态（03 第 6.1 节）。之后执行器从 `JobManager` 中移除。
- **背压**：`in_flight`（已派发、结果还没落库）达到 `MAX_UNCOMMITTED = 200` 时暂停派发，等条目落库后再继续。模型很快时（例如演示模型的 `fast`、本机部署的小模型）引擎可能比写入协程快，不设上限的话写入队列越积越长：进度长时间不更新，暂停、取消这类接口操作也要排在积压后面很久才生效。

### 5.3 一条条目的处理

1. 通过写入协程把条目标记为 running、写 `started_at`，加入 `ProgressTracker` 的处理中集合，推送轨道更新；
2. 按任务快照渲染消息（05 第 2 节），按当前模型配置计算输入预算（05 第 7.1 节），把渲染参数写入 `render_meta_json`（03 第 4.7 节）；
3. 意图识别：超长则截断（05 第 7.3 节）；摘要：超长则分段再合并（05 第 7.4 节）；
4. 发请求，按 05 第 6 节分类错误、重试、等待；每次请求写一条尝试记录；
5. 解析输出（05 第 4 节），失败时发一次纠正请求；
6. 把结果交给写入协程：条目字段、跟随条目同步、任务计数和 tokens、类别颜色（新类别在写入协程里按提交顺序分配序号，保证顺序一致）、模型平均耗时；
7. 移出处理中集合，记录完成时间，推送更新；完成通知置位后移出 `in_flight`（第 5.2 节）。

需要暂停整个任务的情况，处理器返回对应结果，由 `_process` 调用 `request_stop`：

| 情况 | 原因码 | 触发的这一条 |
|---|---|---|
| HTTP 401、403 | `auth_failed` | 放回 pending，不计失败 |
| HTTP 404 | `model_not_found` | 放回 pending，不计失败 |
| 熔断（05 第 6.3 节） | `circuit_breaker` | 保持 failed（它确实失败了） |

### 5.4 暂停、继续、取消

| 操作 | 实现 |
|---|---|
| 暂停 | `request_stop("pause", "user_pause", "已手动暂停")`：设 `stop_requested`，任务状态立即写为 paused（接口马上返回）；不再派发；进行中的条目正常处理完。全部落库后执行器退出 |
| 取消 | 设 `stop_requested = "cancel"`，任务状态写为 cancelled；取消进行中的 asyncio 任务，被打断的条目放回 pending（不计失败）|
| 继续 | 暂停前的执行器还在收尾时，**复用它**：清除 `stop_requested` 并唤醒主循环，不新建，否则两个执行器的任务级闸门叠加，会超出任务并发。没有执行器时新建一个。读取当前模型配置。已经没有待处理条目时（暂停期间恰好做完）直接置为 completed，否则写为 running |
| 重试失败项 | 把 failed 条目置为 pending、清空错误字段，按“继续”启动 |
| 单条重跑 | 条目正在处理时返回 409。否则把它置为 pending（跟随条目先解除 `dedup_of`），提交后：任务 completed 时按“继续”启动；任务 running 时唤醒执行器，它扫到底再从头扫时会捡到这条；任务 paused 时只改条目 |

建任务时没有可处理的条目会直接返回 422 `NO_ITEMS`（04 第 8.1 节），所以新任务至少有一条待处理条目；只有“继续”“重试失败项”时才可能遇到没有待处理条目、直接置为 completed 的情况。

### 5.5 写入与计数

`ResultWriter` 从一个 `asyncio.Queue` 读取操作，每 300 毫秒或攒够 100 个操作提交一次事务。操作类型：

| 操作 | 内容 |
|---|---|
| `ItemUpdate` | 一条条目的字段变化 |
| `FollowersSync` | 主条目结束后，同步全部跟随条目（03 第 6.2 节） |
| `JobDelta` | 计数和 tokens 的增量 |
| `JobStatus` | 状态和原因 |
| `CategoryColor` | 新类别分配颜色序号 |
| `ModelLatency` | 模型平均耗时 |

事务提交成功后，置位这一批操作的完成通知，再把涉及的任务、条目交给 `EventBus` 发布。写入失败时记录日志并重试一次，仍失败则把相关任务暂停（原因码 `write_failed`），并让这一批的完成通知以异常结束，引擎据此把相关条目移出 `in_flight`。

**按批合并**：异步驱动下每条 SQL 都要在线程和事件循环之间往返几次，一批 100 个操作逐条执行要上千次往返，引擎忙的时候一批要几秒才能提交。所以引擎的写入是声明式的（只给出条目和字段，`ItemUpdate`；条目结束时附带计数、tokens、类别、耗时），写入协程在一个事务里：

- 同一条目在这一批里的字段按先后合并，再按字段组合分组，每组一条 `executemany`；
- `JobDelta`（按任务）、`ModelLatency`（按模型，按先后依次代入平均耗时公式）在这一批里汇总后各写一次；
- `FollowersSync` 只对确实有跟随条目的主条目执行（一次查询找出这一批里哪些主条目有跟随条目）；
- 遇到接口的状态变更等自定义操作时，先把攒下的写入落下去再执行它，先后顺序不变。

### 5.6 进度与速度

`ProgressTracker` 保存进行中条目的集合和最近 30 次完成的时间。`running`、`pending`、速度、剩余时间按 03 第 7 节计算，随 `job.updated` 推送；轨道数据随 `tracks.updated` 推送。

### 5.7 程序退出与恢复

退出（托盘“退出”、`/api/system/shutdown`、应用生命周期结束）时：

1. `JobManager.pause_all()`：排队和运行中的任务写为 paused，原因码 `shutdown`；
2. 最多等 3 秒让进行中的请求结束，之后取消剩余的，被打断的条目放回 pending；
3. 写入协程把队列全部提交；
4. 结束所有 SSE 连接：设置 sse-starlette 的退出标志（3.x 为 `sse_starlette.sse.AppStatus.should_exit = True`），每个事件流随即结束；
5. 关闭模型客户端和数据库连接。

第 4 步必须在通知 uvicorn 停止**之前**做。启动器把后端跑在非主线程里，uvicorn 这时不安装信号处理器，sse-starlette 收不到退出通知；界面开着时事件流一直不断，uvicorn 会无限等这些连接关闭，托盘“退出”就卡住了。uvicorn 另设 `timeout_graceful_shutdown=5` 作为最后保险。启动器里各步骤在哪个线程、按什么顺序执行，见 07 第 5.1 节第 9 步。应用生命周期结束时（例如开发模式下按 Ctrl+C）也执行第 1–3、5 步，重复执行没有副作用。

意外退出（崩溃、强制结束进程）时来不及做以上步骤，由下次启动时的恢复逻辑兜底（03 第 8 节第 4、5 步）。

## 6. 文件解析

### 6.1 统一接口

```python
class SourceReader(Protocol):
    def inspect(self) -> FileMeta: ...                                     # 03 第 4.1 节
    def columns(self, sheet: str | None, header_row: int) -> list[Column]: ...
    def iter_rows(self, sheet: str | None, header_row: int,
                  start_row: int | None = None) -> Iterator[Row]: ...      # Row(row_number, values)
```

按扩展名选实现：`csv` → `CsvReader`；`xlsx`、`xls` → `ExcelReader`；`txt`、`md` → `TextReader`。P0 中 `docx`、`pdf` 返回 415。

### 6.2 编码识别（csv、txt、md）

取文件前 1 MB 作为样本（文件不足 1 MB 时就是全文），按顺序判断：

1. 有 BOM：按 BOM 判定（UTF-8、UTF-16 LE / BE）；
2. 样本能按 UTF-8 严格解码：UTF-8；
3. 样本能按 GB18030 严格解码：`gb18030`（本项目的数据以简体中文为主，GBK 文件远比其他编码常见，先试它更可靠）；
4. 否则用 `charset-normalizer` 判断；结果属于 GB2312、GBK、GB18030 一类时统一用 `gb18030`；
5. 仍无法判断：按 `gb18030` 解码并替换无法识别的字符，`FileInfo` 照常返回，预览接口的提示里注明“部分字符可能显示不正确”。

第 4 步是统计判断，准确率不作保证（01 IMP-03 只要求 UTF-8、UTF-8 BOM、GB18030、UTF-16）。已知限制：单字节的西文编码之间可能分不清，例如 Windows-1252（西欧）编码的法语文本会被判成 Windows-1250（中欧），`è` 显示成 `č`。两者在统计上难以区分，偏向任何一方都会让另一方的文件出错，所以不做特殊处理；这类文件先另存为 UTF-8 再上传。

**样本末尾的处理**：1 MB 的截断点很可能落在一个多字节汉字中间，直接严格解码会失败，导致大于 1 MB 的 UTF-8 文件被误判成 GBK、整份乱码。第 2、3 步要用增量解码器解码样本：`codecs.getincrementaldecoder(编码)("strict").decode(样本, final=是否已读到文件末尾)`，`final=False` 时末尾不完整的字节会被暂存而不报错。

### 6.3 分隔符（csv）

用 `csv.Sniffer` 在前 64 KB 中从 `, \t ; |` 里识别；失败时统计前 20 行各候选字符出现次数，取每行次数最稳定且大于 0 的；都不行就用逗号。

### 6.4 Excel

- 用 `python-calamine` 读取 xlsx 和 xls（只读、速度快、内存占用低）；
- 单元格转字符串：空值为空字符串；整数值的浮点数去掉 `.0`（“10023” 而不是 “10023.0”）；日期时间为 `YYYY-MM-DD HH:MM:SS`，时间为零时只保留日期；布尔值为“是”“否”；首尾空白去掉；
- 扩展名是 xlsx 但文件头是 `D0 CF 11 E0`（OLE 容器）：说明文件被加密，返回 `FILE_PARSE_FAILED`，提示“这个 Excel 文件设置了打开密码，请另存为无密码的文件后再上传”；
- 其他读取异常：`FILE_PARSE_FAILED`，提示“文件已损坏或不是有效的 Excel 文件”。

### 6.5 文本

只按 `\r\n`、`\r`、`\n` 切分（正则 `\r\n|\r|\n`），行号从 1 开始，与记事本等编辑器显示的行号一致；去掉每行首尾空白；空行在建任务时记为 skipped。不要用 `str.splitlines()`：它还会在 `\x0b`、`\x0c`、`\x1c`–`\x1e`、`\x85`、`\u2028`、`\u2029` 处断行，行号就对不上了。

### 6.6 行号与列

- 表格类的 `row_number` 是原文件中的行号（从 1 开始，表头行也计入），与用户在 Excel 里看到的行号一致；`header_row = 1` 时第一条数据的行号是 2；
- csv 按**记录**计行号，不按物理行：引号里带换行的一条记录只算一行（Excel 打开它时也只占一行）。`header_row`、`start_row` 都按记录序号理解；
- 列 key 规则见 03 第 4.2 节；
- 数据行里比表头多出来的单元格，按列字母补列 key。

### 6.7 多列拼接

- `labeled`：对每个选中的列，值非空时生成一行 `列标题：值`，按用户选择的顺序用换行连接；
- `plain`：选中列的非空值用换行连接；
- 只选一列时两种方式结果相同，都是值本身；
- 拼接结果为空：该行记为 skipped。

### 6.8 限制与性能

- 每个工作表或文本最多读取 10 万条数据行，超出部分不读，`truncated = true`；
- `inspect` 只读元数据和前 500 行；总行数：Excel 取工作表尺寸，csv、txt 流式计数；
- 预览接口每次只解析请求的那一段行；
- 建任务时流式读取，边读边按 1,000 行一批写入条目。

## 7. 事件推送

- `EventBus`：进程内发布订阅。每个订阅者一个有界队列（容量 2,000）；队列满了说明客户端太慢，直接断开这个连接，客户端会自动重连并重新拉取数据；
- SSE 接口用 `sse-starlette` 的 `EventSourceResponse`，每 15 秒发 `ping`。它默认的 ping 是注释行，前端收不到，要用 `ping_message_factory=lambda: ServerSentEvent(event="ping", data="{}")` 改成具名事件（参数名以所装版本为准）；
- 程序退出时由第 5.7 节第 4 步统一结束所有事件流；
- 单任务事件流在服务端按 250 毫秒的窗口合并：同一条目多次更新只发最后一次，轨道只发最新状态，`job.updated` 每秒最多一次（状态变化时立即发）；
- 事件名和数据结构见 04 第 10 节。

## 8. 前端架构

### 8.1 选择

| 关注点 | 方案 |
|---|---|
| 框架 | Vue 3 组合式 API + `<script setup lang="ts">` |
| 构建 | Vite |
| 样式 | Tailwind CSS（v4，`@tailwindcss/vite` 插件），设计令牌用 CSS 变量，在 `@theme` 中引用 |
| 无样式组件 | Reka UI（对话框、抽屉、下拉、组合框、滑块、开关、标签页、提示等的行为和无障碍） |
| 状态 | Pinia |
| 路由 | Vue Router（history 模式） |
| 表格 | TanStack Table + TanStack Virtual（都只用无样式的核心） |
| 编辑器 | CodeMirror 6（直接用核心包，自己封装组件） |
| 动效 | CSS 过渡 + Web Animations API；需要编排的地方用 Motion for Vue |
| 提示 | vue-sonner |
| 图标 | `@lucide/vue`，描边宽度 1.75 |
| Markdown | markdown-it + DOMPurify（摘要可能含 Markdown） |
| 接口 | openapi-typescript 生成类型 + openapi-fetch |
| 工具 | VueUse |
| 测试 | Vitest + Vue Test Utils；Playwright |

不使用 Element Plus、Ant Design Vue、Naive UI 这类成套组件库：它们的默认外观会把界面拉回后台模板的样子，改皮肤的成本比在 Reka UI 上自绘更高。

### 8.2 接口类型生成

后端启动后执行 `npm run gen:api`：

```json
"gen:api": "npx --yes openapi-typescript@7.13.0 http://127.0.0.1:18765/openapi.json -o src/api/schema.d.ts"
```

用 `npx` 临时运行，避免它对 TypeScript 5 的对等依赖与项目的 TypeScript 6 冲突。

`schema.d.ts` 提交进仓库。后端接口变化后重新生成，类型检查会指出前端需要改的地方。SSE 和试运行的事件数据也在里面：后端自定义 `app.openapi()` 把它们登记进了 `components.schemas`（04 第 10.1 节），前端用 `components["schemas"]["JobLive"]` 这样的写法取类型。

客户端：`createClient<paths>({ baseUrl: import.meta.env.VITE_API_BASE ?? "" })`（SSE 和上传的地址同样加这个前缀，第 1.1 节），在中间件里给所有非 GET 请求加 `X-WenShu-Client: 1`，并把错误响应转换成统一的 `ApiError`（包含 `code`、`message`），由调用处决定是 toast 还是表单内提示。不经过这个客户端的请求（文件上传、试运行的流）也必须带这个请求头，统一从 `api/client.ts` 导出的 `apiHeaders()` 取得。

### 8.3 实时数据

- `useGlobalEvents()`：在 `App.vue` 里建立全局 SSE 连接，更新 jobs store；
- `useJobLive(jobId)`：任务详情页建立单任务 SSE 连接，维护 `JobLive`、轨道、条目缓存；
- 条目缓存：`Map<页号, ItemSummary[]>`，`items.updated` 到达时按 id 更新已缓存的条目；
- 重连成功后重新请求任务详情和当前可见页；
- 试运行是 POST 请求的流，`EventSource` 不支持，用 `fetch` 读取 `ReadableStream` 并按 SSE 格式解析（`api/stream.ts`），支持中途取消（`AbortController`）。

### 8.4 性能约定

- 路由全部懒加载；CodeMirror 只在提示词工坊加载；
- 大数组用 `shallowRef`，条目对象用 `markRaw`，避免深层响应式；
- SSE 数据先进缓冲区，用 `requestAnimationFrame` 合并刷新，每秒最多 10 次；
- 搜索输入停顿 250 毫秒再请求。

### 8.5 构建产物

`npm run build` 输出到 `frontend/dist`，资源带哈希；字体随资源打包。`scripts\build-web.bat`（源码版启动和 `build.bat` 都调用它）把 `dist` 复制到 `backend/app/static`。

## 9. 配置、路径与日志

### 9.1 路径

| 路径 | 打包版 | 源码版、开发 |
|---|---|---|
| 程序目录 `app_dir` | `Path(sys.executable).parent` | `backend/` |
| 静态文件 | `Path(sys._MEIPASS) / "app" / "static"` | `backend/app/static`（开发时用 Vite，可以不存在） |
| 迁移文件 | `Path(sys._MEIPASS) / "app" / "db" / "migrations"` | `backend/app/db/migrations` |
| 数据目录 `data_dir` | 见下 | 见下 |

数据目录按顺序取：环境变量 `WENSHU_DATA_DIR`；`app_dir / "data"`（可写时）；`%LOCALAPPDATA%\WenShu\data`。`启动文枢.bat` 默认把 `WENSHU_DATA_DIR` 设为项目根目录的 `data`，`dev.bat` 设为 `.devdata`。子目录结构见 03 第 10 节。

运行方式（`SystemInfo.run_mode`）：`sys.frozen` 为真是 `exe`；否则 `WENSHU_DEV=1` 是 `dev`；其余是 `source`。

### 9.2 环境变量

| 变量 | 作用 |
|---|---|
| `WENSHU_DATA_DIR` | 指定数据目录（开发时 `dev.bat` 设为项目下的 `.devdata`，避免与正式数据混在一起） |
| `WENSHU_PORT` | 开发时告诉后端自己的端口（引擎调用演示模型要用）；打包后由启动器传入 |
| `WENSHU_DEV` | `1` 表示开发模式：注册 `POST /api/_dev/reset`、日志级别 DEBUG、`/api/system/shutdown` 不退出进程（前端的组件预览路由由 Vite 的开发模式决定，与它无关） |
| `WENSHU_MOCK_FAIL_RATE` | 演示模型随机故障率，默认 `0.02` |
| `WENSHU_LOG_LEVEL` | 覆盖日志级别 |
| `WENSHU_CORS_ORIGINS` | 前端单独部署时放行的来源，逗号分隔，如 `http://127.0.0.1:4173`；不设置则不返回任何 CORS 头 |
| `WENSHU_PYTHON` | 只给批处理脚本用：创建虚拟环境时使用的 Python 解释器路径（07 第 5.5 节） |
| `WENSHU_API_TARGET` | 只给前端开发服务器用：Vite 把 `/api` 等请求代理到哪里，默认 `http://127.0.0.1:18765`；端到端测试设为 `http://127.0.0.1:18766`（07 第 3 节） |

### 9.3 日志

- 标准库 `logging`，写 `data/logs/app.log`，单个 5 MB，保留 5 个；格式 `时间 级别 模块: 消息`；
- 打包后关闭 Uvicorn 的访问日志；错误请求（4xx、5xx）记一行；
- 模型请求在 DEBUG 级别记录地址、模型名、耗时、状态码，不记录密钥和请求头；只有 `WENSHU_LOG_LEVEL=DEBUG` 时才记录消息内容的前 200 字；
- 未捕获的异常记录完整堆栈。

## 10. 安全

| 风险 | 措施 |
|---|---|
| 局域网访问 | 只监听 `127.0.0.1` |
| 跨来源访问 | 默认不返回任何 CORS 头。只有设置了 `WENSHU_CORS_ORIGINS` 时，才用 FastAPI 的 `CORSMiddleware` 对列出的来源放行（允许 `X-WenShu-Client` 请求头），用于前端单独部署 |
| 其他网页借用户的浏览器调用本机接口 | `security.py` 中间件：`Host` 必须是 `127.0.0.1:{端口}` 或 `localhost:{端口}`（防 DNS 重绑定）；除 `GET`、`OPTIONS` 外的 `/api` 请求必须带 `X-WenShu-Client: 1`（跨站请求带自定义头会触发预检，而服务端不放行其他来源，预检必然失败）；`/mock` 不检查 |

**中间件顺序**：`CORSMiddleware` 必须在最外层（Starlette 里最后调用 `add_middleware` 的在最外层），这样跨来源的预检请求先由它应答，不会被 `security.py` 拦下。`security.py` 也不检查 `OPTIONS` 请求，双重保证。

**OpenAPI 安全方案**：在 OpenAPI 里声明一个 apiKey 安全方案（`in: header`，`name: X-WenShu-Client`）并设为全局 `security`，只用于让 `/docs` 出现 Authorize 按钮，真正的检查仍由中间件做（04 第 1 节）。
| 密钥泄露 | Fernet 加密后存库，加密密钥在 `data/secret.key`（首次启动生成）；接口只返回掩码；日志不记录请求头 |
| 上传文件 | 50 MB 上限，在读完请求体前检查；按哈希重命名存放，不执行任何内容；只用解析库读取 |
| 导出 | 文件名去掉 Windows 不允许的字符，写在 `data/exports/` 内 |

`secret.key` 只能防止数据库文件被单独拷走后泄露密钥，挡不住能登录这台电脑的人。这对单用户本机工具是合适的强度，在设置页的数据目录说明里写清楚。

## 11. 测试基础设施

### 11.1 后端测试

任务引擎通过真实的 HTTP 调用演示模型（04 第 11 节），SSE 和试运行是长连接的流，Host 检查还需要知道端口。所以后端测试统一请求一个**真正在监听端口的服务**，不用 `httpx.ASGITransport`（它没有监听端口，引擎连不上 `/mock`；它还要等响应体全部收完，测事件流时会一直挂起）。

`backend/tests/conftest.py`：

- 会话级 fixture：创建临时数据目录，设好 `WENSHU_DATA_DIR`、`WENSHU_MOCK_FAIL_RATE=0`、`WENSHU_DEV=1`；像启动器一样先绑定 `127.0.0.1:0` 拿到空闲端口，设 `WENSHU_PORT`，再把 socket 交给 uvicorn，在后台线程运行，轮询 `/api/health` 直到就绪；结束时按第 5.7 节的顺序关闭；
- `client` fixture：`httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", headers={"X-WenShu-Client": "1"})`；
- 每个测试开始前调用 `POST /api/_dev/reset` 和 `POST /mock/v1/_reset`，互不影响；
- 测试数据文件不存在时，先运行 `scripts/make_testdata.py` 生成到 `testdata/`（08 第 10.2 节）；
- 纯函数模块（渲染、输出解析、切分、编码识别、导出的单元格清理）直接调用函数测试，不经过服务。

### 11.2 端到端测试

见 08 第 10.4 节：Playwright 用自己的端口和全新的数据目录（`.e2edata`）启动后端和 Vite，与开发环境互不干扰。
