# AGENTS.md

> 给参与开发文枢的 AI agent 和开发者。动手之前先读完本文件，再按任务阅读对应文档。

## 项目是什么

文枢（WenShu）是一个 Windows 本机、单用户使用的工具：上传 txt、md、csv、xlsx、xls 文件，按行调用 OpenAI 兼容接口的大模型，批量完成**意图识别**或**文本摘要**；两种任务的提示词和模型都能在界面里修改、试运行；结果可以查看、校对、导出 Excel。

项目前后端分离，源码完整可读。使用者有两种一键启动方式，行为完全一致（启动后端，弹出独立窗口显示界面，托盘常驻）：

- 双击项目根目录的 `启动文枢.bat`：源码版，首次自动建环境、装依赖、构建前端；
- 双击 `release\WenShu\WenShu.exe`：打包版，自带运行环境。

技术栈：后端 Python 3.13 + FastAPI + SQLAlchemy 2（异步）+ SQLite；前端 Vue 3 + Vite + TypeScript + Tailwind CSS + Reka UI；打包 PyInstaller。版本见 `docs/02-architecture.md` 第 2 节。

## 文档地图

| 文档 | 内容 | 谁读 |
|---|---|---|
| `docs/01-requirements.md` | 需求、功能清单（P0 / P1 / P2）、非功能需求、已确认的决策 | 所有人先读 |
| `docs/02-architecture.md` | 技术栈与版本、目录结构、模块职责、任务引擎、文件解析、事件推送、前端架构 | 写代码前必读 |
| `docs/03-database.md` | SQLite 表结构、JSON 字段、状态机、迁移、写入策略 | 后端 |
| `docs/04-api.md` | 全部 HTTP 接口、SSE 事件、错误码、导出列、前端路由 | 前端、后端 |
| `docs/05-llm-and-prompts.md` | 模型调用、两套内置提示词、变量、输出解析、重试、长文本、演示模型 | 后端；提示词页面 |
| `docs/06-ui-design.md` | 视觉语言、设计令牌、组件、页面线框、交互与动效、文案、UI 验收 | 前端 |
| `docs/07-packaging.md` | 本机环境搭建、dev.bat、build.bat、启动器、PyInstaller、发布检查 | 搭环境、打包 |
| `docs/08-plan-and-acceptance.md` | 分阶段任务、每阶段验收、测试用例、交给 agent 的提示语 | 领任务时 |

## 硬性规则

1. **文档是唯一依据。** 字段名、接口路径、状态值、错误码、事件名必须与 03、04 完全一致。
2. **冲突与空白。** 文档之间冲突时以 03、04 为准；文档没写到的地方，选最简单、最符合 01 第 7 节决策的做法。两种情况都要在完成报告里写明。
3. **不扩大范围。** 不加文档里没有的功能，不换技术栈，不引入未列出的重要依赖（小型工具库除外，需在报告里说明理由）。
4. **只听本机。** 后端只监听 `127.0.0.1`。并发上限 20 是硬上限，前后端都要校验。
5. **密钥不外泄。** API Key 不以明文出现在接口返回、日志、导出文件和前端存储里。
6. **离线可用。** 前端不得从网络加载任何资源（CDN、在线字体、远程图标），全部随包分发。
7. **文案。** 界面文案用简体中文，遵守 06 第 9 节；代码标识符用英文；注释用中文。
8. **令牌。** 颜色、字号、间距、圆角、动效时长全部来自 06 第 3 节的设计令牌，组件里不写硬编码色值。
9. **前后端分离。** `frontend/` 不引用 `backend/` 的任何代码或文件，反之亦然；两者只通过 04 的接口通信（02 第 1.1 节）。不要为了省事让前端读后端目录、或让后端渲染页面。唯一的例外是端到端测试：Playwright 可以启动后端、运行 `scripts/make_testdata.py`、读取根目录的 `testdata/`（08 第 10.4 节），前端的应用代码仍然不能引用后端。
10. **README 同步。** 新增或改动了启动、构建、测试命令或环境变量，同一次提交里更新对应的 README（根目录、`backend/`、`frontend/`）。
11. **不提交** `data/`、`.devdata/`、`.e2edata/`、`testdata/`、`scripts/local.env.cmd`、构建产物和任何真实 API Key。`.gitignore` 的目录规则一律以 `/` 开头锚定在根目录（08 第 2 节），否则 `data/` 会把 `frontend/src/components/data/` 的源码一起忽略。
12. **每个阶段结束前**跑完 08 中该阶段的验收清单。

## 目录速览

```
wenshu/
├── AGENTS.md
├── README.md                项目说明
├── 启动文枢.bat              源码版一键启动
├── docs/                    本套文档
├── backend/                 后端工程：FastAPI 应用、任务引擎、启动器、测试，自带 README
├── frontend/                前端工程：Vue 应用、端到端测试，自带 README
├── packaging/               PyInstaller 配置、图标、版本信息
├── scripts/                 dev.bat、setup.bat、prestart.py、build-web.bat、build.bat
└── release/                 打包产物 WenShu.exe（构建生成，不提交）
```

完整结构见 02 第 3 节。

## 常用命令

在项目根目录执行：

| 做什么 | 命令 |
|---|---|
| 首次搭建开发环境 | 见 07 第 2 节 |
| 像使用者一样从源码启动 | 双击 `启动文枢.bat` |
| 启动开发环境（热更新） | `scripts\dev.bat` |
| 只构建前端到 `backend\app\static` | `scripts\build-web.bat` |
| 生成测试数据到 `testdata\` | `backend\.venv\Scripts\python.exe scripts\make_testdata.py` |
| 后端测试 | `backend\.venv\Scripts\python.exe -m pytest backend\tests` |
| 后端检查 | `backend\.venv\Scripts\python.exe -m ruff check backend` |
| 生成前端接口类型（需先启动后端） | `cd frontend && npm run gen:api` |
| 前端类型检查与代码检查 | `cd frontend && npm run typecheck && npm run lint` |
| 前端单元测试 | `cd frontend && npm run test` |
| 端到端测试 | `cd frontend && npm run e2e` |
| 打包 | `scripts\build.bat` |

## 这台机器的注意事项

- Python 一律用 `backend\.venv\Scripts\python.exe`。不要在 Git Bash 里直接敲 `python` 或 `python3`，那是坏掉的别名。创建虚拟环境用的解释器路径写在 `scripts\local.env.cmd` 的 `WENSHU_PYTHON` 里（示例：`C:\Python313\python.exe`）。
- npm 的源已设为 npmmirror，pip 的源为华为云，装依赖不需要改配置。
- 本机只有 JDK 8、Docker 引擎未运行：本项目都用不到。

## 完成的定义

- 实现与文档一致，该阶段验收清单全部通过；
- 新增的后端逻辑有 pytest 用例，关键用户流程有 Playwright 用例；
- 不需要真实 API Key 也能完整演示（使用内置演示模型）；
- `vue-tsc` 无类型错误，ESLint、Ruff 无错误，全部测试通过；
- 亮色、暗色两套主题都检查过。

## 完成报告格式

```text
阶段：N
完成的任务：T?-1、T?-2……
验收结果：逐条列出，通过 / 未通过（原因）
文档问题：冲突或没写清楚的地方，以及你的处理方式
新增的依赖：名称、版本、理由（没有就写“无”）
下一阶段注意：……
```
