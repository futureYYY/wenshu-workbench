/**
 * 任务详情页的单任务 SSE（02 第 8.3 节）：维护 JobLive、并行轨道，并把条目更新交给结果表。
 * 事件先进缓冲区，用 requestAnimationFrame 合并刷新，每秒最多 10 次。
 */
import { onBeforeUnmount, ref, shallowRef, watch, type Ref } from "vue"
import { jobsApi } from "@/api/endpoints"
import { openEventStream } from "@/api/events"
import type { ItemSummary, ItemsUpdatedEvent, Job, JobLive, Track, TracksUpdatedEvent } from "@/api/types"
import { createCoalescer } from "@/utils/sse"

export interface JobLiveHandle {
  job: Ref<Job | null>
  tracks: Ref<Track[]>
  loading: Ref<boolean>
  error: Ref<unknown>
  /** 重新拉取任务详情和轨道 */
  refresh: () => Promise<void>
  /** 合并一份较新的数据（接口返回、全局事件流）；乐观更新期间保留被 hold 的字段 */
  patchLocal: (patch: Partial<Job>) => void
  /** 乐观更新（06 第 7.2 节）：界面立刻改掉；接口返回前，实时事件里的这些字段不覆盖它 */
  hold: (patch: Partial<Job>) => void
  /** 接口返回后解除 hold；revert 为 true（接口失败）时恢复成 hold 之前的值 */
  release: (revert: boolean) => void
}

export interface JobLiveOptions {
  /** 一批条目更新（已合并） */
  onItems?: (items: ItemSummary[]) => void
  /** 断线重连成功：结果表应重新拉取当前可见页 */
  onReconnected?: () => void
}

export function useJobLive(jobId: Ref<number | null>, options: JobLiveOptions = {}): JobLiveHandle {
  const job = shallowRef<Job | null>(null)
  const tracks = shallowRef<Track[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)
  let close: (() => void) | null = null
  let pendingLive: JobLive | null = null
  let pendingTracks: Track[] | null = null
  let held: { patch: Partial<Job>; before: Partial<Job> } | null = null

  const items = createCoalescer<ItemSummary, number>({
    key: (item) => item.id,
    onFlush: (list) => options.onItems?.(list),
  })

  // 任务和轨道的更新也走同一个节奏：每帧合并、每秒最多 10 次
  const frame = createCoalescer<"job" | "tracks", string>({
    key: (k) => k,
    onFlush: (keys) => {
      if (keys.includes("job") && pendingLive && job.value) {
        // JobLive 不含快照和来源，合并到已有的 Job 上；乐观更新的字段在接口返回前保持不变
        job.value = { ...job.value, ...pendingLive, ...(held?.patch ?? {}) }
        pendingLive = null
      }
      if (keys.includes("tracks") && pendingTracks) {
        tracks.value = pendingTracks
        pendingTracks = null
      }
    },
  })

  async function refresh(): Promise<void> {
    const id = jobId.value
    if (id === null) return
    loading.value = true
    try {
      const [detail, trackList] = await Promise.all([jobsApi.get(id), jobsApi.tracks(id)])
      if (jobId.value !== id) return
      job.value = detail
      tracks.value = trackList
      error.value = null
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  function patchLocal(patch: Partial<Job>) {
    if (job.value) job.value = { ...job.value, ...patch, ...(held?.patch ?? {}) }
  }

  function hold(patch: Partial<Job>) {
    const current = job.value
    if (!current) return
    const before: Record<string, unknown> = {}
    for (const key of Object.keys(patch) as (keyof Job)[]) before[key] = current[key]
    held = { patch, before: before as Partial<Job> }
    job.value = { ...current, ...patch }
  }

  function release(revert: boolean) {
    const h = held
    held = null
    if (revert && h && job.value) job.value = { ...job.value, ...h.before }
  }

  function connect(id: number) {
    close?.()
    close = openEventStream({
      jobId: id,
      onEvent: (name, data) => {
        if (!data || typeof data !== "object") return
        if (name === "job.updated") {
          const live = data as JobLive
          if (live.id !== id) return
          pendingLive = live
          frame.push(["job"])
        } else if (name === "items.updated") {
          const event = data as ItemsUpdatedEvent
          if (event.job_id === id) items.push(event.items)
        } else if (name === "tracks.updated") {
          const event = data as TracksUpdatedEvent
          if (event.job_id !== id) return
          pendingTracks = event.items
          frame.push(["tracks"])
        }
      },
      onReconnected: () => {
        void refresh()
        options.onReconnected?.()
      },
    })
  }

  watch(
    jobId,
    (id) => {
      close?.()
      close = null
      items.cancel()
      frame.cancel()
      held = null
      job.value = null
      tracks.value = []
      if (id !== null) {
        void refresh()
        connect(id)
      }
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    close?.()
    close = null
    items.cancel()
    frame.cancel()
  })

  return { job, tracks, loading, error, refresh, patchLocal, hold, release }
}
