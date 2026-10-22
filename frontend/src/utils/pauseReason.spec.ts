import { describe, expect, it } from "vitest"
import type { PauseReasonCode } from "@/api/types"
import { pauseNotice } from "./pauseReason"

function paused(code: PauseReasonCode | null, reason = "说明") {
  return { status: "paused" as const, status_reason: reason, status_reason_code: code }
}

describe("暂停原因", () => {
  it("手动暂停、没有原因码、不是已暂停时不提示", () => {
    expect(pauseNotice(paused("user_pause", "已手动暂停"))).toBeNull()
    expect(pauseNotice(paused(null, ""))).toBeNull()
    expect(pauseNotice({ status: "running", status_reason: "", status_reason_code: null })).toBeNull()
  })

  it("鉴权失败、模型不存在：去修改模型和继续", () => {
    for (const code of ["auth_failed", "model_not_found"] as const) {
      const notice = pauseNotice(paused(code, "模型密钥无效或无权限（HTTP 401）"))
      expect(notice).toEqual({ code, text: "模型密钥无效或无权限（HTTP 401）", fixModel: true, openLogs: false })
    }
  })

  it("熔断、程序退出：只有继续", () => {
    for (const code of ["circuit_breaker", "shutdown"] as const) {
      expect(pauseNotice(paused(code))).toMatchObject({ code, fixModel: false, openLogs: false })
    }
  })

  it("保存结果失败：打开日志目录和继续", () => {
    expect(pauseNotice(paused("write_failed", "保存结果失败，请查看日志"))).toMatchObject({ fixModel: false, openLogs: true })
  })

  it("按原因码判断，不看中文文案", () => {
    // 文案里有“密钥”但原因码是熔断：不显示“去修改模型”
    expect(pauseNotice(paused("circuit_breaker", "连续 10 条请求失败，最后一次：密钥无效"))?.fixModel).toBe(false)
  })
})
