/**
 * 暂停原因的提示和操作（06 第 6.3、6.4 节）。按 status_reason_code 判断，不匹配中文文案：
 * - auth_failed、model_not_found：“去修改模型”和“继续”；
 * - circuit_breaker、shutdown：“继续”；
 * - write_failed：“打开日志目录”和“继续”；
 * - user_pause（手动暂停）不提示。
 */
import type { JobSummary, PauseReasonCode } from "@/api/types"

export interface PauseNotice {
  code: PauseReasonCode
  /** 后端给的中文说明（status_reason） */
  text: string
  /** 显示“去修改模型” */
  fixModel: boolean
  /** 显示“打开日志目录” */
  openLogs: boolean
}

type PauseFields = Pick<JobSummary, "status" | "status_reason" | "status_reason_code">

/** 已暂停、且不是手动暂停时返回要显示的提示；其余情况返回 null */
export function pauseNotice(job: PauseFields): PauseNotice | null {
  const code = job.status_reason_code
  if (job.status !== "paused" || code === null || code === "user_pause") return null
  return {
    code,
    text: job.status_reason,
    fixModel: code === "auth_failed" || code === "model_not_found",
    openLogs: code === "write_failed",
  }
}
