/** 界面状态：主题、实时连接、全局浮层、待执行的删除。 */
import { defineStore } from "pinia"
import { computed, ref, watch } from "vue"
import type { ConnectionState } from "@/api/events"
import type { ThemeSetting } from "@/api/types"
import { withViewTransition } from "@/design/motion"
import type { ThemeName } from "@/design/palette"

const THEME_KEY = "wenshu.theme"

function readStoredTheme(): ThemeSetting {
  try {
    const value = localStorage.getItem(THEME_KEY)
    if (value === "light" || value === "dark" || value === "system") return value
  } catch {
    // 无法访问 localStorage 时跟随系统
  }
  return "system"
}

const darkQuery =
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null

/** 当前是否有浮层（对话框、抽屉、下拉、命令面板）打开着：Esc 先关浮层，没有浮层时才清除筛选 */
export function isOverlayOpen(): boolean {
  return (
    document.querySelector(
      "[role='dialog'][data-state='open'], [role='alertdialog'][data-state='open'], [role='menu'][data-state='open'], [role='listbox'][data-state='open'], [data-reka-popper-content-wrapper]",
    ) !== null
  )
}

export const useUiStore = defineStore("ui", () => {
  const themeSetting = ref<ThemeSetting>(readStoredTheme())
  const systemDark = ref<boolean>(darkQuery?.matches ?? false)
  darkQuery?.addEventListener?.("change", (event: MediaQueryListEvent) => {
    systemDark.value = event.matches
  })

  const resolvedTheme = computed<ThemeName>(() => {
    if (themeSetting.value === "system") return systemDark.value ? "dark" : "light"
    return themeSetting.value
  })

  function applyTheme(theme: ThemeName) {
    document.documentElement.setAttribute("data-theme", theme)
  }

  watch(resolvedTheme, (theme) => {
    void withViewTransition(() => applyTheme(theme))
  })

  /** 修改主题设置（写入 localStorage；同步到后端由调用方负责） */
  function setTheme(theme: ThemeSetting) {
    themeSetting.value = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // 忽略
    }
  }

  /** 在亮色、暗色之间切换，返回新的设置值 */
  function toggleTheme(): ThemeSetting {
    const next: ThemeSetting = resolvedTheme.value === "dark" ? "light" : "dark"
    setTheme(next)
    return next
  }

  // 实时连接状态：断开时页面栏显示“正在重新连接”
  const connection = ref<ConnectionState>("connecting")
  const reconnecting = computed(() => connection.value === "reconnecting")

  // 全局浮层
  const paletteOpen = ref(false)
  const shortcutsOpen = ref(false)

  // 可撤销删除的待执行函数：关闭窗口前立即执行
  const pendingCommits = new Set<() => void>()
  function addPendingCommit(commit: () => void): () => void {
    pendingCommits.add(commit)
    return () => pendingCommits.delete(commit)
  }
  function flushPendingCommits() {
    for (const commit of Array.from(pendingCommits)) {
      pendingCommits.delete(commit)
      commit()
    }
  }

  // 当前页面登记的“清除筛选”处理（Esc 在没有浮层时调用）
  const clearFilterHandler = ref<(() => boolean) | null>(null)

  return {
    themeSetting,
    resolvedTheme,
    setTheme,
    toggleTheme,
    connection,
    reconnecting,
    paletteOpen,
    shortcutsOpen,
    addPendingCommit,
    flushPendingCommits,
    clearFilterHandler,
  }
})
