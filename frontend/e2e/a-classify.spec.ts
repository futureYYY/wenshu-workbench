/**
 * 场景 A 意图识别主流程（08 第 10.4 节）：
 * 首页拖入 intent_200.xlsx → 自动选中“用户问题”列 → 意图识别、并发 5、处理 100 条 → 开始；
 * 并行轨道最多 5 行；完成后线网图至少 3 条线路；点击一条线路，结果表只剩该意图；
 * 按 Enter 打开条目抽屉，看到发送内容；导出 xlsx，下载成功。
 */
import { expect, test } from "@playwright/test"
import { dropFile, resetBackend, testdata, waitForCompleted } from "./helpers"

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test("意图识别主流程", async ({ page }) => {
  await page.goto("/")
  await expect(page.locator("[data-dropzone]")).toBeVisible()

  await dropFile(page, "[data-dropzone]", testdata("intent_200.xlsx"))
  await expect(page).toHaveURL(/\/new\?file=\d+/)

  // 自动选中“用户问题”列（按平均字数推荐）
  const column = page.getByRole("button", { name: "取消选择“用户问题”列" })
  await expect(column).toHaveAttribute("aria-pressed", "true")
  await page.getByRole("button", { name: "下一站：设任务" }).click()

  // 意图识别、并发 5、处理 100 条（都是默认值）
  await expect(page.getByRole("radio", { name: /意图识别/ })).toHaveAttribute("aria-checked", "true")
  await expect(page.getByRole("slider", { name: "并发" })).toHaveAttribute("aria-valuenow", "5")
  await expect(page.getByRole("radio", { name: "100" })).toHaveAttribute("aria-checked", "true")
  await page.getByRole("button", { name: "下一站：确认" }).click()

  await expect(page.getByText(/做意图识别/)).toBeVisible()
  await page.getByTestId("start-job").click()
  await expect(page).toHaveURL(/\/jobs\/\d+$/)

  // 并行轨道最多 5 行
  const rows = page.locator(".ws-tracks__row")
  await expect(rows.first()).toBeVisible()
  expect(await rows.count()).toBeLessThanOrEqual(5)
  expect(await page.locator(".ws-tracks__car").count()).toBeLessThanOrEqual(5)

  await waitForCompleted(page)

  // 线网图至少 3 条线路
  const terminals = page.locator("button.ws-linemap__label[data-terminal]")
  await expect.poll(async () => terminals.count()).toBeGreaterThanOrEqual(3)

  // 点击一条线路，结果表只剩该意图
  const first = terminals.first()
  const label = ((await first.locator(".ws-linemap__name").textContent()) ?? "").trim()
  expect(label).not.toBe("")
  await first.click()
  await expect(page.locator(".ws-detail__chips")).toContainText(label)
  await expect
    .poll(async () => {
      const texts = await page.locator(".ws-grid__body .ws-badge__text").allTextContents()
      return texts.length > 0 && texts.every((t) => t.trim() === label)
    })
    .toBeTruthy()

  // 按 Enter 打开条目抽屉，看到发送内容
  await page.locator(".ws-grid__body .ws-grid__row").first().click()
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/item=\d+/)
  const drawer = page.getByRole("dialog")
  await expect(drawer).toBeVisible()
  await drawer.getByRole("tab", { name: "发送内容" }).click()
  await expect(drawer.locator(".ws-item__msg").first()).toBeVisible()
  await expect(drawer).toContainText("请识别下面这段文本的意图")
  await page.keyboard.press("Escape")
  await expect(drawer).toBeHidden()

  // 导出 xlsx
  await page.getByTestId("export-menu").click()
  const downloadPromise = page.waitForEvent("download")
  await page.getByRole("menuitem", { name: "全部条目" }).first().click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/)
})
