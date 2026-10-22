/**
 * 任务的暂停、继续、取消、重试失败项、删除和导出（06 第 7.2、9 节）：
 * 界面立刻改变，接口失败时回滚并 toast 说明原因；toast 与按钮同名（“已暂停”“已继续”…）。
 */
import { exportJob, jobsApi, type ExportFormat, type ExportScope } from "@/api/endpoints"
import type { ItemFilters, Job, JobSummary } from "@/api/types"
import { useJobsStore } from "@/stores/jobs"
import { useUiStore } from "@/stores/ui"
import { saveBlob } from "@/utils/download"
import { formatNumber } from "@/utils/format"
import { notify, notifyError, notifyUndo } from "@/utils/toast"

type AnyJob = JobSummary | Job

/** 页面自己持有的任务数据（任务详情页的 useJobLive）：乐观更新时一起改，接口返回前不被实时事件覆盖 */
export interface LocalJobState {
  hold: (patch: Partial<JobSummary>) => void
  release: (revert: boolean) => void
}

export function useJobActions(onChange?: (job: Job) => void, local?: LocalJobState) {
  const jobs = useJobsStore()
  const ui = useUiStore()

  function optimistic(job: AnyJob, patch: Partial<JobSummary>) {
    jobs.upsert({ ...(job as JobSummary), ...patch })
  }

  async function run(job: AnyJob, patch: Partial<JobSummary>, call: () => Promise<Job>, message: string): Promise<Job | null> {
    const before = jobs.byId(job.id) ?? (job as JobSummary)
    optimistic(job, patch)
    local?.hold(patch)
    try {
      const next = await call()
      jobs.upsert(next)
      local?.release(false)
      onChange?.(next)
      notify(message)
      return next
    } catch (e) {
      jobs.upsert(before)
      local?.release(true)
      notifyError(e)
      return null
    }
  }

  const pause = (job: AnyJob) =>
    run(
      job,
      { status: "paused", status_reason: "已手动暂停", status_reason_code: "user_pause" },
      () => jobsApi.pause(job.id),
      "已暂停",
    )

  const resume = (job: AnyJob) =>
    run(job, { status: "running", status_reason: "", status_reason_code: null }, () => jobsApi.resume(job.id), "已继续")

  const cancel = (job: AnyJob) => run(job, { status: "cancelled" }, () => jobsApi.cancel(job.id), "已取消")

  async function retryFailed(job: AnyJob): Promise<Job | null> {
    const count = job.progress.failed
    return run(job, { status: "running" }, () => jobsApi.retryFailed(job.id), `已重新排队 ${formatNumber(count)} 条`)
  }

  /**
   * 删除：没有结果的任务立刻从列表消失，toast 带“撤销”，6 秒后才调用接口；
   * 有结果的任务由调用方先弹确认对话框，确认后用 immediate=true 直接删除，不再提供撤销（06 第 7.2 节）。
   */
  async function remove(job: AnyJob, immediate: boolean, onRemoved?: () => void): Promise<void> {
    const commit = async () => {
      try {
        await jobsApi.remove(job.id)
        jobs.remove(job.id)
        onRemoved?.()
      } catch (e) {
        jobs.unhide(job.id)
        notifyError(e)
      }
    }
    if (immediate) {
      jobs.hide(job.id)
      await commit()
      notify(`已删除任务“${job.name}”`)
      return
    }
    jobs.hide(job.id)
    let release: () => void = () => undefined
    const flush = notifyUndo(
      `已删除任务“${job.name}”`,
      async () => {
        release()
        await commit()
      },
      () => {
        release()
        jobs.unhide(job.id)
      },
    )
    release = ui.addPendingCommit(flush) as () => void
  }

  async function exportFile(jobId: number, format: ExportFormat, scope: ExportScope, filters: ItemFilters = {}) {
    try {
      const { blob, filename } = await exportJob(jobId, format, scope, filters)
      saveBlob(blob, filename)
      notify(`已导出 ${filename}`)
    } catch (e) {
      notifyError(e)
    }
  }

  return { pause, resume, cancel, retryFailed, remove, exportFile }
}

/** 有没有结果：成功条数大于 0（06 第 6.3 节）。有结果的任务删除前要确认 */
export function hasResults(job: AnyJob): boolean {
  return job.progress.succeeded > 0
}
