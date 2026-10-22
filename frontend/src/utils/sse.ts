/**
 * SSE 相关的纯函数：
 * - SseParser：把 fetch 读到的文本流按 SSE 格式拆成事件（试运行的 POST 流用，EventSource 不支持 POST）；
 * - createCoalescer：实时数据的合并缓冲，同一条目多次更新只保留最后一次，
 *   用 requestAnimationFrame 统一刷新，每秒最多 10 次（02 第 8.4 节、06 第 7.7 节）。
 */

export interface SseMessage {
  event: string
  data: string
  id: string | null
}

export class SseParser {
  private buffer = ""
  private eventName = ""
  private dataLines: string[] = []
  private lastId: string | null = null

  /**
   * 喂入一段文本，返回其中已经完整的事件。
   * 换行可以是 \r\n、\n 或 \r；末尾单独的 \r 先留着，等下一块看后面是不是 \n（\r\n 可能被拆在两块里）。
   */
  feed(chunk: string): SseMessage[] {
    this.buffer += chunk
    const out: SseMessage[] = []
    const buf = this.buffer
    let start = 0
    let i = 0
    while (i < buf.length) {
      const ch = buf[i]
      if (ch !== "\n" && ch !== "\r") {
        i += 1
        continue
      }
      if (ch === "\r" && i + 1 >= buf.length) break
      const line = buf.slice(start, i)
      i += ch === "\r" && buf[i + 1] === "\n" ? 2 : 1
      start = i
      const message = this.processLine(line)
      if (message) out.push(message)
    }
    this.buffer = buf.slice(start)
    return out
  }

  /** 流结束时调用：处理最后一行，并派发还没遇到空行的事件 */
  flush(): SseMessage[] {
    const out: SseMessage[] = []
    const rest = this.buffer.replace(/\r$/, "")
    this.buffer = ""
    if (rest) {
      for (const line of rest.split(/\r\n|\n|\r/)) {
        const message = this.processLine(line)
        if (message) out.push(message)
      }
    }
    const last = this.dispatch()
    if (last) out.push(last)
    return out
  }

  private processLine(line: string): SseMessage | null {
    if (line === "") return this.dispatch()
    if (line.startsWith(":")) return null
    const colon = line.indexOf(":")
    const field = colon >= 0 ? line.slice(0, colon) : line
    let value = colon >= 0 ? line.slice(colon + 1) : ""
    if (value.startsWith(" ")) value = value.slice(1)
    if (field === "event") this.eventName = value
    else if (field === "data") this.dataLines.push(value)
    else if (field === "id") this.lastId = value
    return null
  }

  private dispatch(): SseMessage | null {
    if (this.dataLines.length === 0 && !this.eventName) return null
    const message: SseMessage = {
      event: this.eventName || "message",
      data: this.dataLines.join("\n"),
      id: this.lastId,
    }
    this.eventName = ""
    this.dataLines = []
    return message
  }
}

export interface Coalescer<T> {
  /** 放入一批更新；同一个键只保留最后一次 */
  push(items: Iterable<T>): void
  /** 立即刷新（例如组件卸载前） */
  flushNow(): void
  /** 丢弃缓冲并停止调度 */
  cancel(): void
  /** 缓冲里还有多少个键 */
  readonly size: number
}

export interface CoalescerOptions<T, K> {
  key: (item: T) => K
  onFlush: (items: T[]) => void
  /** 两次刷新的最小间隔，毫秒；默认 100（每秒最多 10 次） */
  minInterval?: number
  schedule?: (callback: () => void) => number
  cancelSchedule?: (handle: number) => void
  now?: () => number
}

export function createCoalescer<T, K>(options: CoalescerOptions<T, K>): Coalescer<T> {
  const minInterval = options.minInterval ?? 100
  const schedule =
    options.schedule ??
    ((cb: () => void) =>
      typeof requestAnimationFrame === "function"
        ? requestAnimationFrame(() => cb())
        : (setTimeout(cb, 16) as unknown as number))
  const cancelSchedule =
    options.cancelSchedule ??
    ((h: number) =>
      typeof cancelAnimationFrame === "function" ? cancelAnimationFrame(h) : clearTimeout(h))
  const now = options.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()))

  const pending = new Map<K, T>()
  let handle: number | null = null
  let lastFlush = -Infinity

  const run = () => {
    handle = null
    if (pending.size === 0) return
    if (now() - lastFlush < minInterval) {
      handle = schedule(run)
      return
    }
    flush()
  }

  const flush = () => {
    if (handle !== null) {
      cancelSchedule(handle)
      handle = null
    }
    if (pending.size === 0) return
    const items = Array.from(pending.values())
    pending.clear()
    lastFlush = now()
    options.onFlush(items)
  }

  return {
    push(items: Iterable<T>) {
      for (const item of items) {
        const k = options.key(item)
        // 先删再放，保证顺序是“最后一次更新”的顺序
        pending.delete(k)
        pending.set(k, item)
      }
      if (pending.size > 0 && handle === null) handle = schedule(run)
    },
    flushNow: flush,
    cancel() {
      if (handle !== null) cancelSchedule(handle)
      handle = null
      pending.clear()
    },
    get size() {
      return pending.size
    },
  }
}
