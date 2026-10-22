/**
 * 场景 B 摘要（08 第 10.4 节）：粘贴 3 行长文本 → 文本摘要 → 完成；
 * 打开对照阅读，看到压缩比，悬停要点时来源段落高亮。
 */
import { expect, test } from "@playwright/test"
import { longLine, resetBackend, startFromPaste, waitForCompleted } from "./helpers"

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test("文本摘要与对照阅读", async ({ page }) => {
  const text = [longLine("第一份工单", 30), longLine("第二份工单", 24), longLine("第三份工单", 36)].join("\n")
  await startFromPaste(page, text)

  await page.getByRole("button", { name: "下一站：设任务" }).click()
  await page.getByRole("radio", { name: /文本摘要/ }).click()
  await expect(page.getByRole("radio", { name: /文本摘要/ })).toHaveAttribute("aria-checked", "true")
  await page.getByRole("button", { name: "下一站：确认" }).click()
  await expect(page.getByText(/做文本摘要/)).toBeVisible()
  await page.getByTestId("start-job").click()
  await expect(page).toHaveURL(/\/jobs\/\d+$/)

  await waitForCompleted(page)

  // 单击结果行进入对照阅读
  await page.locator(".ws-grid__body .ws-grid__row").first().click()
  await expect(page).toHaveURL(/\/read\/\d+$/)

  // 看到压缩比
  await expect(page.locator(".ws-gauge__ratio-value")).toContainText("×")

  // 悬停要点时来源段落高亮
  const point = page.locator(".ws-trace__point").first()
  await expect(point).toBeVisible()
  await point.hover()
  await expect(page.locator(".ws-trace__segment.is-active").first()).toBeVisible()
})
