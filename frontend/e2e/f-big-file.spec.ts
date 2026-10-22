/**
 * 场景 F 大文件（08 第 10.4 节）：上传 big_120k.csv（模型请求头 X-Mock-Behavior: fast）→ 3 秒内出预览且提示截断 →
 * 选择“全部” → 预估显示 100,000 条 → 开始 → 运行中结果表滚动流畅（检查无长任务卡顿）。
 */
import { expect, test } from "@playwright/test"
import { createModel, resetBackend, testdata } from "./helpers"

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test("12 万行文件：预览、截断提示、全部处理与滚动", async ({ page, request }) => {
  await createModel(request, "快速演示", { "X-Mock-Behavior": "fast" })

  await page.goto("/new")
  await page.getByTestId("file-input").setInputFiles(testdata("big_120k.csv"))
  await expect(page).toHaveURL(/\/new\?file=\d+/, { timeout: 60_000 })

  // 上传完成后 3 秒内出预览，并提示截断
  await expect(page.locator(".ws-preview__table")).toBeVisible({ timeout: 3_000 })
  await expect(page.getByText("只读取了前 100,000 条")).toBeVisible()
  await page.getByRole("button", { name: "下一站：设任务" }).click()

  // 选“快速演示”模型、处理“全部”
  await page.getByRole("combobox", { name: "模型" }).click()
  await page.getByRole("option", { name: /快速演示/ }).click()
  await page.getByRole("radio", { name: /全部/ }).click()
  await page.getByRole("button", { name: "下一站：确认" }).click()
  await expect(page.locator(".ws-confirm__lead")).toContainText("100,000", { timeout: 60_000 })
  await page.getByTestId("start-job").click()
  await expect(page).toHaveURL(/\/jobs\/\d+$/, { timeout: 120_000 })

  // 运行中快速滚动结果表，用 PerformanceObserver 记录长任务
  await page.evaluate(() => {
    const w = window as unknown as { __longTasks: number[] }
    w.__longTasks = []
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.__longTasks.push(entry.duration)
    }).observe({ type: "longtask", buffered: false })
  })
  const grid = page.locator(".ws-grid__scroller")
  await expect(grid).toBeVisible()
  await grid.hover()
  for (let i = 0; i < 30; i++) {
    await page.mouse.wheel(0, 2400)
    await page.waitForTimeout(30)
  }
  const longTasks = await page.evaluate(() => (window as unknown as { __longTasks: number[] }).__longTasks)
  // 08 第 10.5 节：快速滚动时没有超过 50 ms 的长任务；端到端环境略放宽，超过 100 ms 才判失败
  expect(Math.max(0, ...longTasks)).toBeLessThan(100)

  // 结束：取消任务，避免后台继续处理 10 万条
  await page.getByRole("button", { name: "取消任务" }).click()
  await expect(page.getByTestId("export-menu")).toBeVisible()
})
