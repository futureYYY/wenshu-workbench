/**
 * 场景 D 鉴权失败恢复（08 第 10.4 节）：接入一个模型（地址 http://127.0.0.1:18766/mock/v1、自定义请求头
 * X-Mock-Behavior: auth）→ 建任务 → 任务自动暂停，提示条显示原因和“去修改模型” → 点“去修改模型”删除该请求头 →
 * 返回点“继续” → 任务完成。
 */
import { expect, test } from "@playwright/test"
import { MOCK_BASE_URL, resetBackend, startFromPaste, waitForCompleted } from "./helpers"

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test("鉴权失败后修改模型并继续", async ({ page }) => {
  // 接入模型：用界面填写表单
  await page.goto("/models?new=1")
  const form = page.getByRole("dialog")
  await expect(form).toBeVisible()
  await form.locator("#mf-name").fill("鉴权测试")
  await form.locator("#mf-base").fill(MOCK_BASE_URL)
  await form.locator(".ws-combo__field").fill("wenshu-demo")
  await form.getByRole("button", { name: "高级" }).click()
  await form.getByRole("button", { name: "添加" }).click()
  await form.getByLabel("请求头 1 的名称").fill("X-Mock-Behavior")
  await form.getByLabel("请求头 1 的值").fill("auth")
  await form.getByTestId("save-model").click()
  await expect(form).toBeHidden()
  await expect(page.getByText("鉴权测试", { exact: true })).toBeVisible()

  // 第一个真实模型会自动成为两种任务的默认模型；建任务
  await startFromPaste(page, ["我要退货", "快递到哪了", "会员怎么取消", "投诉客服态度", "发票怎么开"].join("\n"))
  await page.getByRole("button", { name: "下一站：设任务" }).click()
  await page.getByRole("button", { name: "下一站：确认" }).click()
  await expect(page.getByText(/鉴权测试/)).toBeVisible()
  await page.getByTestId("start-job").click()
  await expect(page).toHaveURL(/\/jobs\/\d+$/)
  const jobUrl = page.url()

  // 任务自动暂停（原因码 auth_failed），提示条显示原因和“去修改模型”
  const banner = page.getByTestId("pause-banner")
  await expect(banner).toContainText("已暂停：模型密钥无效或无权限（HTTP 401）", { timeout: 30_000 })
  await expect(banner.getByRole("button", { name: "去修改模型" })).toBeVisible()

  // 去修改模型：删除请求头
  await banner.getByRole("button", { name: "去修改模型" }).click()
  await expect(page).toHaveURL(/\/models\?edit=\d+/)
  const edit = page.getByRole("dialog")
  await expect(edit).toBeVisible()
  await edit.getByRole("button", { name: "高级" }).click()
  await edit.getByRole("button", { name: "删除这个请求头" }).click()
  await edit.getByTestId("save-model").click()
  await expect(edit).toBeHidden()

  // 返回点“继续”
  await page.goto(jobUrl)
  await page.getByTestId("pause-banner").getByRole("button", { name: "继续" }).click()
  await waitForCompleted(page)
  await expect(page.getByRole("radio", { name: /成功/ })).toContainText("5")
})
