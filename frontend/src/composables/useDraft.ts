/**
 * 提示词草稿：每次修改 500 ms 后存入 localStorage（键 wenshu.prompt-draft.{id}，06 第 6.7 节）。
 */
import { onBeforeUnmount } from "vue"

const PREFIX = "wenshu.prompt-draft."

export interface DraftHandle<T> {
  /** 读取已保存的草稿，没有时返回 null */
  read: () => T | null
  /** 计划保存（500 ms 防抖） */
  schedule: (value: T) => void
  /** 立即保存 */
  saveNow: (value: T) => void
  /** 删除草稿 */
  clear: () => void
}

export function draftKey(id: number | string): string {
  return `${PREFIX}${id}`
}

export function useDraft<T>(key: () => string | null, delay = 500): DraftHandle<T> {
  let timer: number | undefined
  let pendingValue: { value: T } | null = null

  function write(value: T) {
    const k = key()
    if (!k) return
    try {
      localStorage.setItem(k, JSON.stringify({ savedAt: new Date().toISOString(), value }))
    } catch {
      // 存储已满或不可用时放弃草稿
    }
  }

  function read(): T | null {
    const k = key()
    if (!k) return null
    try {
      const raw = localStorage.getItem(k)
      if (!raw) return null
      const parsed = JSON.parse(raw) as { value?: T }
      return parsed.value ?? null
    } catch {
      return null
    }
  }

  function schedule(value: T) {
    pendingValue = { value }
    window.clearTimeout(timer)
    timer = window.setTimeout(() => {
      if (pendingValue) write(pendingValue.value)
      pendingValue = null
    }, delay)
  }

  function saveNow(value: T) {
    window.clearTimeout(timer)
    pendingValue = null
    write(value)
  }

  function clear() {
    window.clearTimeout(timer)
    pendingValue = null
    const k = key()
    if (!k) return
    try {
      localStorage.removeItem(k)
    } catch {
      // 忽略
    }
  }

  onBeforeUnmount(() => {
    if (pendingValue) write(pendingValue.value)
    window.clearTimeout(timer)
  })

  return { read, schedule, saveNow, clear }
}
