/**
 * SSE 订阅（04 第 10 节）。
 * - 全局流 /api/events：首页、任务中心、窗口标题；
 * - 单任务流 /api/events?job_id=：任务详情页。
 * EventSource 会自动重连；连接断开时通知“正在重新连接”，重连成功后通知调用方重新拉取数据。
 */
import { apiUrl } from "./client"

export type ConnectionState = "connecting" | "open" | "reconnecting"

export const EVENT_NAMES = [
  "job.created",
  "job.updated",
  "job.deleted",
  "items.updated",
  "tracks.updated",
  "ping",
] as const

export type EventName = (typeof EVENT_NAMES)[number]

export interface EventStreamOptions {
  jobId?: number | null
  onEvent: (name: EventName, data: unknown) => void
  onStateChange?: (state: ConnectionState) => void
  /** 断线后重新连上时调用：用接口数据覆盖本地状态 */
  onReconnected?: () => void
}

/** 打开一个事件流，返回关闭函数 */
export function openEventStream(options: EventStreamOptions): () => void {
  let source: EventSource | null = null
  let closed = false
  let hadError = false
  let retryTimer: number | undefined
  let retryDelay = 1000

  const url = apiUrl(options.jobId != null ? `/api/events?job_id=${options.jobId}` : "/api/events")

  const scheduleRetry = () => {
    if (closed) return
    window.clearTimeout(retryTimer)
    retryTimer = window.setTimeout(connect, retryDelay)
    retryDelay = Math.min(retryDelay * 2, 10_000)
  }

  function connect() {
    if (closed) return
    options.onStateChange?.(hadError ? "reconnecting" : "connecting")
    const es = new EventSource(url)
    source = es
    es.onopen = () => {
      retryDelay = 1000
      options.onStateChange?.("open")
      if (hadError) {
        hadError = false
        options.onReconnected?.()
      }
    }
    es.onerror = () => {
      hadError = true
      options.onStateChange?.("reconnecting")
      // 连接被彻底关闭（例如后端返回了错误状态）时浏览器不会自动重连，自己重试
      if (es.readyState === EventSource.CLOSED) {
        es.close()
        scheduleRetry()
      }
    }
    for (const name of EVENT_NAMES) {
      es.addEventListener(name, (event: Event) => {
        const message = event as MessageEvent<string>
        let data: unknown
        try {
          data = message.data ? JSON.parse(message.data) : null
        } catch {
          data = null
        }
        options.onEvent(name, data)
      })
    }
  }

  connect()

  return () => {
    closed = true
    window.clearTimeout(retryTimer)
    source?.close()
    source = null
  }
}
