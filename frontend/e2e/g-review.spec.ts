/**
 * 场景 G 人工复核（08 第 10.4 节）：
 * - 意图识别完成后打开第一条，按 E，改成提示词里列出的另一个类别 → 抽屉显示“人工修正”和修正前的类别，
 *   结果表这一行出现修正标记 → 复核筛选选“人工修正”只剩这一条 → 撤销修正后标记消失；
 * - 文本摘要完成后在对照阅读里修改摘要 → 显示“人工修改”，展开“模型原摘要”能看到原来的摘要 →
 *   导出的 CSV 里“摘要”是修改后的内容，“修正前摘要”是模型原来的摘要。
 */
import { expect, test } from "@playwright/test"
import { longLine, resetBackend, startFromPaste, waitForCompleted } from "./helpers"

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

// 演示模型在文本里看到类别名就选它（05 第 8.2 节），第一行一定识别成“投诉”
const CLASSIFY_LINES = [
  "我要投诉快递员态度很差",
  "想咨询一下流量套餐的价格",
  "帮我办理宽带续费",
  "给你们提个建议，客服时间延长一点",
]

test("修正意图：只能选提示词里的类别，修正前后都看得到，可以撤销", async ({ page }) => {
  await startFromPaste(page, CLASSIFY_LINES.join("\n"))
  await page.getByRole("button", { name: "下一站：设任务" }).click()
  await page.getByRole("button", { name: "下一站：确认" }).click()
  await page.getByTestId("start-job").click()
  await expect(page).toHaveURL(/\/jobs\/\d+$/)
  await waitForCompleted(page)

  // 打开第一条，按 E 打开“修改意图”菜单，改成“建议”
  const rows = page.locator(".ws-grid__body .ws-grid__row")
  await rows.first().click()
  await page.keyboard.press("Enter")
  const drawer = page.getByRole("dialog")
  await expect(drawer).toBeVisible()
  await expect(drawer.locator(".ws-badge__text").first()).toHaveText("投诉")
  await page.keyboard.press("e")
  await expect(page.getByRole("menuitem", { name: "投诉（模型识别）" })).toBeVisible()
  await page.getByRole("menuitem", { name: "建议", exact: true }).click()

  await expect(drawer.getByText("人工修正", { exact: true })).toBeVisible()
  await expect(drawer.getByText("修正前", { exact: true })).toBeVisible()
  await expect(drawer.locator(".ws-badge__text").first()).toHaveText("建议")
  await expect(drawer.getByTestId("toggle-reviewed")).toHaveAttribute("aria-pressed", "true")   // 修正时自动标记已复核

  await page.keyboard.press("Escape")
  await expect(drawer).toBeHidden()
  await expect(rows.first().getByLabel("人工修正")).toBeVisible()

  // 复核筛选：只看人工修正
  await page.getByRole("combobox", { name: "按复核状态筛选" }).click()
  await page.getByRole("option", { name: "人工修正" }).click()
  await expect(rows).toHaveCount(1)

  // 撤销修正
  await rows.first().click()
  await page.keyboard.press("Enter")
  await expect(drawer).toBeVisible()
  await drawer.getByRole("button", { name: "撤销修正" }).click()
  await expect(drawer.getByText("人工修正", { exact: true })).toBeHidden()
  await expect(drawer.locator(".ws-badge__text").first()).toHaveText("投诉")
})

test("修改摘要：显示人工修改和模型原摘要，导出用修改后的内容", async ({ page, request }) => {
  await startFromPaste(page, [longLine("第一份工单", 20), longLine("第二份工单", 16)].join("\n"))
  await page.getByRole("button", { name: "下一站：设任务" }).click()
  await page.getByRole("radio", { name: /文本摘要/ }).click()
  await page.getByRole("button", { name: "下一站：确认" }).click()
  await page.getByTestId("start-job").click()
  await expect(page).toHaveURL(/\/jobs\/\d+$/)
  const jobId = Number(/\/jobs\/(\d+)$/.exec(page.url())?.[1])
  await waitForCompleted(page)

  await page.locator(".ws-grid__body .ws-grid__row").first().click()
  await expect(page).toHaveURL(/\/read\/\d+$/)
  const edited = "人工改写的摘要：两份工单都要在三个工作日内回访确认。"
  await page.getByTestId("edit-summary").click()
  await page.getByTestId("summary-editor").fill(edited)
  await page.getByTestId("save-summary").click()

  await expect(page.locator(".ws-trace__tag")).toHaveText("人工修改")
  await expect(page.locator(".ws-trace__summary")).toContainText(edited)
  await page.getByRole("button", { name: /模型原摘要/ }).click()
  await expect(page.locator(".ws-reading__original-text")).toContainText("演示摘要")

  // 导出（04 第 9 节）：摘要是修改后的，修正前摘要是模型原来的
  const response = await request.get(`/api/jobs/${jobId}/export?format=csv`)
  expect(response.ok(), await response.text()).toBeTruthy()
  const csv = await response.text()
  expect(csv).toContain("修正前摘要")
  expect(csv).toContain(edited)
  expect(csv).toContain("演示摘要")
})
