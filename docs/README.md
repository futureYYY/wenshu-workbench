# 文枢开发文档

这套文档用来交给 AI agent，从零实现“文枢”：一个 Windows 本机工具，上传 txt、csv、Excel，按行调用 OpenAI 兼容接口的大模型，批量做意图识别或文本摘要。

## 怎么用

1. 新建一个空的项目目录，把 `AGENTS.md` 放在根目录，把 `docs/` 整个放进去。
2. 先自己读一遍 `docs/01-requirements.md` 的第 7 节“已确认的决策”，有不同意见先改文档。
3. 按 `docs/08-plan-and-acceptance.md` 的阶段，一次交给 agent 一个阶段。提示语模板在 08 第 11 节，复制过去改一下阶段号即可。
4. 每个阶段让 agent 跑完验收清单、交完成报告，你确认后再进入下一阶段。阶段 1 完成后，后端（阶段 2）和前端（阶段 3）可以交给两个 agent 同时做。

如果你用的 IDE 不会自动读取 `AGENTS.md`，把它的内容放进这个 IDE 的“项目规则”里。

## 文档清单

| 文件 | 内容 |
|---|---|
| `AGENTS.md` | 给 agent 的总入口：硬性规则、命令、完成的定义 |
| `docs/01-requirements.md` | 需求说明 |
| `docs/02-architecture.md` | 技术架构 |
| `docs/03-database.md` | 数据库设计 |
| `docs/04-api.md` | 接口设计 |
| `docs/05-llm-and-prompts.md` | 提示词与模型调用 |
| `docs/06-ui-design.md` | UI 设计与交互规范 |
| `docs/07-packaging.md` | 环境搭建、开发、打包与启动 |
| `docs/08-plan-and-acceptance.md` | 开发计划、验收与测试 |

`文枢-完整设计方案.md` 是以上全部内容合并成的单个文件，方便通读，或者交给只能读单个文件的工具。
