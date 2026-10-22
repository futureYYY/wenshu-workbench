/**
 * 场景 C 提示词（08 第 10.4 节）：在默认意图识别提示词的类别里加一行“- 催单：催促尽快发货或处理” → 保存，版本 +1 →
 * 试运行文本“我要催单，怎么还没发货”，结果为“催单”（演示模型会选中文本里出现的类别名）→ 打开历史，恢复上一版本。
 */
import { expect, test } from "@playwright/test"
import { resetBackend } from "./helpers"

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test("提示词保存、试运行与恢复版本", async ({ page }) => {
  await page.goto("/prompts")
  await expect(page).toHaveURL(/\/prompts\/\d+$/)

  const version = page.locator(".ws-prompts__version")
  await expect(version).toBeVisible()
  const before = Number(((await version.textContent()) ?? "v0").replace(/\D/g, ""))

  // 在系统提示词末尾加一行类别
  const systemEditor = page.locator(".ws-editor").first().locator(".cm-content")
  await systemEditor.click()
  await page.keyboard.press("Control+End")
  await page.keyboard.press("Enter")
  await page.keyboard.insertText("- 催单：催促尽快发货或处理")
  await expect(page.getByText("有未保存的修改")).toBeVisible()

  await page.getByTestId("save-prompt").click()
  await expect(page.getByText(`已保存为 v${before + 1}`)).toBeVisible()
  await expect(version).toHaveText(`v${before + 1}`)

  // 试运行
  await page.getByTestId("playground-sample").fill("我要催单，怎么还没发货")
  await page.getByTestId("playground-run").click()
  const result = page.getByTestId("playground-result")
  await expect(result).toBeVisible({ timeout: 30_000 })
  await expect(result).toContainText("催单")

  // 打开历史，恢复上一版本
  await page.getByRole("button", { name: "历史" }).click()
  const drawer = page.getByRole("dialog")
  await expect(drawer).toBeVisible()
  await drawer.getByRole("button", { name: new RegExp(`^v${before}\\b`) }).click()
  await drawer.getByRole("button", { name: "恢复此版本" }).click()
  await expect(page.getByText(`已恢复为 v${before}（新版本 v${before + 2}）`)).toBeVisible()
  await expect(version).toHaveText(`v${before + 2}`)
})
