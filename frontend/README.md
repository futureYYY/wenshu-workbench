# 文枢前端

文枢的界面：Vue 3 + Vite + TypeScript + Tailwind CSS + Reka UI。前端是一个独立工程，只通过 HTTP 接口和 SSE 事件与后端通信（接口定义见 `docs/04-api.md`），不引用 `backend/` 的任何代码或文件。

## 运行要求

| 项 | 版本 |
|---|---|
| Node.js | 24（Vite 8 要求 ≥ 22.12），本机 24.12.0 |
| npm | 11，源已设为 npmmirror |
| 浏览器 | 新版 Edge 或 Chrome（端到端测试用本机 Edge） |
| 后端 | 开发和端到端测试需要 `backend/.venv` 已建好（见 `backend/README.md`） |

## 安装

```bat
cd frontend
npm install
```

字体（Noto Sans SC、Overpass、Overpass Mono）都来自 Fontsource 的 npm 包，随 `npm install` 安装、随构建产物分发，界面不从网络加载任何资源。

## 开发

后端需要运行在 `127.0.0.1:18765`，Vite 把 `/api`、`/mock`、`/docs`、`/docs-assets`、`/openapi.json` 代理过去：

```bat
rem 项目根目录：同时启动后端（热更新）和前端（热更新）
scripts\dev.bat

rem 或者只启动前端（后端已经在 18765 运行）
cd frontend
npm run dev
```

打开 http://127.0.0.1:5173 。Vite 开发模式（`npm run dev`）下还有组件预览页 http://127.0.0.1:5173/_dev/components ，展示每个组件的每种状态，可以切换主题；它由 Vite 的开发模式决定，与后端的 `WENSHU_DEV` 无关。

代理目标可以用环境变量 `WENSHU_API_TARGET` 改，默认 `http://127.0.0.1:18765`。它只影响开发服务器，正式构建不受影响；端到端测试把它设为自己启动的后端 `http://127.0.0.1:18766`。代理带 `changeOrigin`，转发后的 `Host` 是后端地址，才能通过后端的 Host 检查。

## 构建

```bat
npm run build
```

产物在 `frontend/dist`（资源带哈希，字体在 `dist/assets`）。由后端托管时用项目根目录的 `scripts\build-web.bat`，它会构建并复制到 `backend\app\static`。

## 生成接口类型

前端的接口类型由后端的 OpenAPI 生成，不要手写：

```bat
rem 先启动后端（18765），再在 frontend 目录执行
npm run gen:api
```

它用 `npx` 临时运行 `openapi-typescript@7.13.0`（它要求 TypeScript 5，和本项目的 TypeScript 6 冲突，所以不装进项目），输出到 `src/api/schema.d.ts`，这个文件要提交。

> 仓库里的 `schema.d.ts` 初始版本是在没有运行环境的机器上按后端 schemas 手工整理的，结构与生成结果一致。第一次在本机启动后端后请运行一次 `npm run gen:api` 覆盖，再跑 `npm run typecheck`；如果有差异，只需要调整 `src/api/types.ts`（类型别名）和 `src/api/endpoints.ts`（接口封装）。

组件和 store 只从 `src/api/types.ts` 取类型、只调用 `src/api/endpoints.ts` 里的函数。不经过 openapi-fetch 的请求（文件上传、试运行的流、SSE、导出下载）同样带 `X-WenShu-Client: 1`，地址和请求头统一从 `src/api/client.ts` 的 `apiUrl()`、`apiHeaders()` 取得。

## 单独部署

前端可以脱离后端单独部署，用构建变量 `VITE_API_BASE` 指向后端地址；后端用环境变量 `WENSHU_CORS_ORIGINS` 放行前端所在的来源。例如用 `npm run preview`（4173 端口）：

```bat
rem 后端（另一个窗口）
set "WENSHU_CORS_ORIGINS=http://127.0.0.1:4173"
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18765

rem 前端
cd frontend
set "VITE_API_BASE=http://127.0.0.1:18765"
npm run build
npm run preview
```

也可以把 `VITE_API_BASE=...` 写进 `frontend/.env.local`（不提交，示例见 `.env.example`）。`VITE_API_BASE` 默认为空，表示与页面同源。

## 设计令牌与组件

- 设计令牌：`src/design/tokens.css`（颜色、字号、间距、圆角、层级、动效时长，亮暗两套），在 `src/design/base.css` 的 `@theme` 里接入 Tailwind；组件里不写硬编码色值；
- 线路色分配和对比度规则：`src/design/palette.ts`；动效常量和“减少动态效果”判断：`src/design/motion.ts`；
- 主题：`<html data-theme="light|dark">`，`index.html` 里的内联脚本在样式加载前读取 `localStorage` 的 `wenshu.theme`，避免闪白；
- 组件预览页：开发模式下的 `/_dev/components`。

## 测试

```bat
rem 类型检查与代码检查
npm run typecheck
npm run lint

rem 单元测试（vitest + jsdom）：线路色、格式化、线网图几何、SSE 合并缓冲、暂停原因
npm run test

rem 端到端测试（Playwright，本机 Edge）
npm run e2e
```

端到端测试（`docs/08-plan-and-acceptance.md` 第 10.4 节）自己启动一套前后端，用独立的端口和数据目录，不影响开发环境和正在使用的文枢：

| 项 | 值 |
|---|---|
| 后端 | `backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18766`，环境变量 `WENSHU_PORT=18766`、`WENSHU_DATA_DIR=<项目根>\.e2edata`、`WENSHU_DEV=1`、`WENSHU_MOCK_FAIL_RATE=0`（另把 `WENSHU_MODELS_FILE` 指向一个不存在的文件，不导入本机的模型配置） |
| 前端 | `npm run dev -- --port 5174`，`WENSHU_API_TARGET=http://127.0.0.1:18766` |
| 浏览器 | `baseURL` 为 http://127.0.0.1:5174，`channel: "msedge"`（本机 Edge，不需要 `npx playwright install`） |
| 数据目录 | 项目根目录的 `.e2edata`，每次运行前删除重建（不提交） |
| 测试数据 | 项目根目录的 `testdata/`，`e2e/global-setup.ts` 发现缺文件、或生成脚本改过（`testdata/.make_testdata.sha256` 对不上）时用 `backend\.venv\Scripts\python.exe scripts\make_testdata.py` 生成（不提交） |

- 每个场景开始前（`beforeEach`）调用 `POST /api/_dev/reset`（只在 `WENSHU_DEV=1` 时注册）和 `POST /mock/v1/_reset`，场景之间不共享数据；
- 需要 `X-Mock-Behavior` 的场景（D 鉴权失败、F 大文件），新建一个地址为 `http://127.0.0.1:18766/mock/v1`、带该请求头的模型；
- 前提：`backend\.venv` 已安装 `requirements-dev.txt`（生成测试数据要用 openpyxl、xlwt）；
- 端到端测试可以启动后端、运行 `scripts/make_testdata.py`、读取 `testdata/`，这是 AGENTS.md 第 9 条（前后端互不引用）的明文例外；前端的应用代码仍然不能引用后端。

覆盖 `docs/08-plan-and-acceptance.md` 第 10.4 节的场景 A–G：意图识别主流程、摘要与对照阅读、提示词保存/试运行/恢复版本、鉴权失败恢复、暂停继续、12 万行大文件、人工复核（修正意图、修改摘要）。

## 目录

```
frontend/
├── index.html               挂载点 #app 和主题防闪烁脚本
├── vite.config.ts           开发服务器代理、构建输出 dist
├── vitest.config.ts
├── playwright.config.ts     端到端测试：启动后端 18766 和 Vite 5174，数据目录 .e2edata
├── eslint.config.js         ESLint（vue、typescript-eslint、prettier）
├── e2e/                     端到端测试（场景 A–G）、global-setup.ts（生成 testdata/）、helpers.ts
├── public/favicon.svg       Logo（与 packaging/icon.svg 相同）
└── src/
    ├── main.ts              字体、样式、Pinia、路由
    ├── App.vue              外壳：导航栏、页面栏、全局浮层、全局快捷键、窗口标题
    ├── router/index.ts      路由表（全部懒加载）
    ├── api/                 schema.d.ts（生成）、types.ts、client.ts、endpoints.ts、events.ts（SSE）、stream.ts（试运行流）
    ├── types/               lucide-vue.d.ts：@lucide/vue 的类型声明（新用到一个图标要在这里补一行）
    ├── stores/              settings、models、prompts、jobs、files、newJob、ui
    ├── composables/         useJobLive、useGlobalEvents、useShortcuts、useDraft、useFileIntake、useJobActions…
    ├── design/              tokens.css、fonts.css、base.css、palette.ts、motion.ts
    ├── components/
    │   ├── base/            Button、Input、Select、Slider、Switch、Tabs、Drawer、Dialog、Tooltip、StatusChip…
    │   ├── metro/           LineBadge、StationDot、MetroStepper、LineProgress、LineMap、ParallelTracks、ExpressTrace、CompressionGauge
    │   ├── data/            DataGrid（结果表）、PreviewGrid（数据预览与选列）
    │   └── editor/          PromptEditor（CodeMirror 6）、JsonView
    ├── features/            home、new-job、jobs、job-detail、reading、prompts、models、settings、command-palette、drop-overlay、dev-components
    └── utils/               format、text、keyboard、sse、markdown、errors、toast、download、pauseReason
```
