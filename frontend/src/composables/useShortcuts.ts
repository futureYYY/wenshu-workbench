/** 键盘快捷键（06 第 7.3 节）：组件挂载时登记，卸载时自动移除。 */
import { onBeforeUnmount, onMounted } from "vue"
import { isTypingTarget, matchShortcut } from "@/utils/keyboard"

export interface ShortcutOptions {
  /** 焦点在输入框里时也生效（默认只有带 Ctrl/Alt 的组合键在输入框内生效） */
  allowInInput?: boolean
  /** 额外的生效条件 */
  when?: () => boolean
  /** 匹配后是否阻止默认行为，默认 true */
  preventDefault?: boolean
}

function hasModifier(spec: string): boolean {
  const s = spec.toLowerCase()
  return s.includes("ctrl+") || s.includes("alt+") || s.includes("mod+")
}

/** 登记一个或多个快捷键；handler 返回 false 表示没有处理（不阻止默认行为） */
export function useShortcut(
  specs: string | string[],
  handler: (event: KeyboardEvent) => void | boolean,
  options: ShortcutOptions = {},
): void {
  const list = Array.isArray(specs) ? specs : [specs]
  const listener = (event: KeyboardEvent) => {
    if (event.defaultPrevented && !options.allowInInput) return
    if (event.isComposing) return
    for (const spec of list) {
      if (!matchShortcut(event, spec)) continue
      const typing = isTypingTarget(event.target)
      if (typing && !options.allowInInput && !hasModifier(spec)) return
      if (options.when && !options.when()) return
      const handled = handler(event)
      if (handled !== false && options.preventDefault !== false) event.preventDefault()
      return
    }
  }
  onMounted(() => window.addEventListener("keydown", listener))
  onBeforeUnmount(() => window.removeEventListener("keydown", listener))
}
