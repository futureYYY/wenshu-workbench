/** toast 的统一入口（vue-sonner）。文案遵守 06 第 9 节：动作和结果同名，不写“操作成功”。 */
import { toast } from "vue-sonner"
import { ApiError } from "@/api/client"

/** 普通结果提示，默认 4 秒 */
export function notify(message: string, description?: string): void {
  toast(message, { description, duration: 4000 })
}

/** 错误提示：接口错误直接用后端的中文说明 */
export function notifyError(error: unknown, fallback = "没有完成，请重试"): void {
  const message = error instanceof ApiError ? error.message : error instanceof Error && error.message ? error.message : fallback
  toast(message, { duration: 6000 })
}

/** 带操作按钮的提示，6 秒 */
export function notifyAction(message: string, label: string, onClick: () => void, onAutoClose?: () => void): void {
  toast(message, {
    duration: 6000,
    action: { label, onClick },
    onAutoClose,
  })
}

/**
 * 可撤销的删除（06 第 7.2 节）：立刻从界面消失，6 秒后才真正执行；
 * 点“撤销”则调用 onUndo。返回立即执行的函数（关闭窗口前调用）。
 */
export function notifyUndo(message: string, commit: () => void | Promise<void>, onUndo: () => void): () => void {
  let settled = false
  const run = () => {
    if (settled) return
    settled = true
    void commit()
  }
  const timer = window.setTimeout(run, 6000)
  toast(message, {
    duration: 6000,
    action: {
      label: "撤销",
      onClick: () => {
        if (settled) return
        settled = true
        window.clearTimeout(timer)
        onUndo()
      },
    },
  })
  return () => {
    window.clearTimeout(timer)
    run()
  }
}
