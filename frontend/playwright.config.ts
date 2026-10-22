import { mkdirSync, rmSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig } from "@playwright/test"

/**
 * 端到端测试（08 第 10.4 节）：自己启动一套前后端，用独立的端口（后端 18766、Vite 5174）和全新的数据目录
 * （项目根目录的 .e2edata），与开发环境互不干扰。使用本机已安装的 Edge（channel: "msedge"）。
 * 端到端测试和根目录的 testdata/ 是 AGENTS.md 第 9 条的明文例外：这里可以启动后端、运行 scripts/make_testdata.py，
 * 前端的应用代码仍然只通过 HTTP 接口与后端通信。
 */
const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, "..")
const backendDir = path.join(root, "backend")
const python =
  process.platform === "win32"
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python")

export const E2E_DATA_DIR = path.join(root, ".e2edata")
export const BACKEND_PORT = 18766
export const WEB_PORT = 5174

// 删除并重建 .e2edata。globalSetup（e2e/global-setup.ts）也会确认它存在；真正的清空放在这里，
// 因为 Playwright 先启动 webServer 再执行 globalSetup，那时后端已经打开了数据库，Windows 上删不掉。
// 主进程加载配置时执行；worker 进程也会加载本文件，那时不清理。
if (!process.env.TEST_WORKER_INDEX) {
  rmSync(E2E_DATA_DIR, { recursive: true, force: true })
  mkdirSync(E2E_DATA_DIR, { recursive: true })
}

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    channel: "msedge",
    viewport: { width: 1600, height: 1000 },
    locale: "zh-CN",
    acceptDownloads: true,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        WENSHU_PORT: String(BACKEND_PORT),
        WENSHU_DATA_DIR: E2E_DATA_DIR,
        // 开发模式才注册 POST /api/_dev/reset，每个场景开始前用它清空数据
        WENSHU_DEV: "1",
        WENSHU_MOCK_FAIL_RATE: "0",
        // 不导入本机的 backend/models.local.json：否则真实模型会成为默认模型，测试会去调用真实接口
        WENSHU_MODELS_FILE: path.join(E2E_DATA_DIR, "models-e2e-none.json"),
      },
    },
    {
      command: `npm run dev -- --port ${WEB_PORT}`,
      cwd: here,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        WENSHU_API_TARGET: `http://127.0.0.1:${BACKEND_PORT}`,
      },
    },
  ],
})
