/**
 * 场景 E 暂停继续（08 第 10.4 节）：并发 2、处理 50 条 → 运行中按 P 暂停 → 断言状态“已暂停”，
 * 轨道上的条目处理完后为空闲 → 再按 P 继续 → 完成，成功数为 50。
 */
import { expect, test } from "@playwright/test"
import { resetBackend, startFromPaste, waitForCompleted } from "./helpers"

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test("暂停与继续", async ({ page }) => {
  const lines = Array.from({ length: 50 }, (_, i) => `第 ${i + 1} 条：我想问一下订单 ${10000 + i} 的退款进度`)
  await startFromPaste(page, lines.join("\n"))
  await page.getByRole("button", { name: "下一站：设任务" }).click()

  // 并发 2：键盘 Home 到 1，再 → 加 1
  const slider = page.getByRole("slider", { name: "并发" })
  await slider.focus()
  await page.keyboard.press("Home")
  await page.keyboard.press("ArrowRight")
  await expect(slider).toHaveAttribute("aria-valuenow", "2")
  await page.getByRole("button", { name: "下一站：确认" }).click()
  await expect(page.getByText("并发 2", { exact: false })).toBeVisible()
  await page.getByTestId("start-job").click()
  await expect(page).toHaveURL(/\/jobs\/\d+$/)

  // 运行中按 P 暂停
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible()
  await expect(page.locator(".ws-tracks__car").first()).toBeVisible()
  await page.locator("body").click({ position: { x: 5, y: 500 } })
  await page.keyboard.press("p")
  await expect(page.getByRole("button", { name: "继续" }).first()).toBeVisible()
  await expect(page.getByText("已暂停，正在处理的条目都已完成")).toBeVisible({ timeout: 30_000 })

  // 再按 P 继续
  await page.keyboard.press("p")
  await waitForCompleted(page)
  await expect(page.getByRole("radio", { name: /成功/ })).toContainText("50")
})
