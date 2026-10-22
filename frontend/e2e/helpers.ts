/** 端到端测试的公用步骤。 */
import { existsSync, readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { expect, type APIRequestContext, type Page } from "@playwright/test"

const here = path.dirname(fileURLToPath(import.meta.url))

/** 后端自己的端口（playwright.config.ts 启动的后端）：模型地址要填它（后端调用自己的演示模型接口） */
export const BACKEND_PORT = 18766
export const MOCK_BASE_URL = `http://127.0.0.1:${BACKEND_PORT}/mock/v1`

/** 项目根目录的测试数据（08 第 10.2 节），由 globalSetup 在缺文件时用 scripts/make_testdata.py 生成 */
export const TESTDATA = path.resolve(here, "..", "..", "testdata")

export function testdata(name: string): string {
  const file = path.join(TESTDATA, name)
  if (!existsSync(file)) {
    throw new Error(`缺少测试数据 ${file}。请运行 backend\\.venv\\Scripts\\python.exe scripts\\make_testdata.py（见 frontend/README.md 的“端到端测试”）。`)
  }
  return file
}

/**
 * 每个场景开始前调用（08 第 10.4 节）：清空任务、文件、自建的提示词和模型，设置恢复默认，并重置演示模型的统计。
 * 请求经 Vite 开发服务器转发到后端；非 GET 请求要带 X-WenShu-Client。
 */
export async function resetBackend(request: APIRequestContext): Promise<void> {
  for (const url of ["/api/_dev/reset", "/mock/v1/_reset"]) {
    const response = await request.post(url, { headers: { "X-WenShu-Client": "1" } })
    expect(response.ok(), `${url}：${response.status()} ${await response.text()}`).toBeTruthy()
  }
}

const MIME: Record<string, string> = {
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".xls": "application/vnd.ms-excel",
  ".csv": "text/csv",
  ".txt": "text/plain",
  ".md": "text/markdown",
}

/** 把本地文件拖放到页面上的某个元素（模拟从资源管理器拖入） */
export async function dropFile(page: Page, selector: string, filePath: string): Promise<void> {
  const name = path.basename(filePath)
  const b64 = readFileSync(filePath).toString("base64")
  const type = MIME[path.extname(filePath).toLowerCase()] ?? ""
  const dataTransfer = await page.evaluateHandle(
    ({ b64, name, type }) => {
      const binary = atob(b64)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
      const dt = new DataTransfer()
      dt.items.add(new File([bytes], name, { type }))
      return dt
    },
    { b64, name, type },
  )
  await page.dispatchEvent(selector, "dragenter", { dataTransfer })
  await page.dispatchEvent(selector, "dragover", { dataTransfer })
  await page.dispatchEvent(selector, "drop", { dataTransfer })
}

/** 通过接口新建一个模型（非 GET 请求要带 X-WenShu-Client） */
export async function createModel(
  request: APIRequestContext,
  name: string,
  headers: Record<string, string> = {},
): Promise<{ id: number }> {
  const response = await request.post("/api/models", {
    headers: { "X-WenShu-Client": "1" },
    data: { name, base_url: MOCK_BASE_URL, model: "wenshu-demo", extra_headers: headers },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  return (await response.json()) as { id: number }
}

/** 新建任务第一站：粘贴文本开始 */
export async function startFromPaste(page: Page, text: string): Promise<void> {
  await page.goto("/new?paste=1")
  await page.getByTestId("paste-text").fill(text)
  await page.getByRole("button", { name: "开始", exact: true }).click()
  await expect(page.getByText("第一条将这样发给模型：")).toBeVisible()
}

/** 等任务详情页进入“已完成”（页头出现导出按钮） */
export async function waitForCompleted(page: Page, timeout = 150_000): Promise<void> {
  await expect(page.getByTestId("export-menu")).toBeVisible({ timeout })
}

/** 生成长文本：若干句话拼成一行 */
export function longLine(seed: string, sentences: number): string {
  const parts: string[] = []
  for (let i = 0; i < sentences; i++) {
    parts.push(`${seed}的第${i + 1}个要点说明了客户反映的问题和客服给出的处理办法，需要在三个工作日内回访确认结果。`)
  }
  return parts.join("")
}
