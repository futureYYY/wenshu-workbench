/** 全局任务列表（首页、任务中心、窗口标题），由全局 SSE 实时更新。 */
import { defineStore } from "pinia"
import { computed, ref, shallowRef } from "vue"
import { jobsApi } from "@/api/endpoints"
import type { JobDeletedEvent, JobSummary } from "@/api/types"
import type { EventName } from "@/api/events"

export function isActiveStatus(status: JobSummary["status"]): boolean {
  return status === "running" || status === "queued" || status === "paused"
}

export function isFinishedStatus(status: JobSummary["status"]): boolean {
  return status === "completed" || status === "cancelled"
}

export const useJobsStore = defineStore("jobs", () => {
  const map = shallowRef(new Map<number, JobSummary>())
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<unknown>(null)
  /** 乐观删除中、暂时隐藏的任务 */
  const hidden = ref(new Set<number>())

  function setMany(items: JobSummary[], replace = false) {
    const next = replace ? new Map<number, JobSummary>() : new Map(map.value)
    for (const job of items) next.set(job.id, job)
    map.value = next
  }

  function upsert(job: JobSummary) {
    const next = new Map(map.value)
    next.set(job.id, job)
    map.value = next
  }

  function remove(id: number) {
    if (!map.value.has(id)) return
    const next = new Map(map.value)
    next.delete(id)
    map.value = next
  }

  function hide(id: number) {
    hidden.value = new Set(hidden.value).add(id)
  }

  function unhide(id: number) {
    const next = new Set(hidden.value)
    next.delete(id)
    hidden.value = next
  }

  const all = computed(() =>
    Array.from(map.value.values())
      .filter((j) => !hidden.value.has(j.id))
      .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id),
  )

  /** 运行中、排队中或已暂停 */
  const active = computed(() => all.value.filter((j) => isActiveStatus(j.status)))

  /** 真正在跑的任务（窗口标题、导航栏圆点、托盘提示） */
  const running = computed(() => all.value.filter((j) => j.status === "running" || j.status === "queued"))

  /** 最近 8 个已结束的任务 */
  const recentFinished = computed(() =>
    all.value
      .filter((j) => isFinishedStatus(j.status))
      .sort((a, b) => (b.finished_at ?? b.updated_at).localeCompare(a.finished_at ?? a.updated_at))
      .slice(0, 8),
  )

  function byId(id: number): JobSummary | null {
    return map.value.get(id) ?? null
  }

  async function load(): Promise<void> {
    loading.value = true
    try {
      const page = await jobsApi.list({ limit: 100 })
      setMany(page.items, true)
      loaded.value = true
      error.value = null
    } catch (e) {
      error.value = e
      throw e
    } finally {
      loading.value = false
    }
  }

  /** 处理全局事件流的一条事件 */
  function applyEvent(name: EventName, data: unknown) {
    if (!data || typeof data !== "object") return
    if (name === "job.created" || name === "job.updated") {
      upsert(data as JobSummary)
    } else if (name === "job.deleted") {
      remove((data as JobDeletedEvent).job_id)
    }
  }

  return {
    map,
    loaded,
    loading,
    error,
    hidden,
    all,
    active,
    running,
    recentFinished,
    byId,
    load,
    setMany,
    upsert,
    remove,
    hide,
    unhide,
    applyEvent,
  }
})
