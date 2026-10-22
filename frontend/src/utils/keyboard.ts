/** 键盘快捷键的匹配与显示（06 第 7.3 节）。 */

/** 焦点是否在可输入的元素里（单字母快捷键在输入框内不生效） */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  if (tag === "TEXTAREA" || tag === "SELECT") return true
  if (tag === "INPUT") {
    const type = (target as HTMLInputElement).type
    return !["checkbox", "radio", "button", "submit", "reset", "range", "color", "file"].includes(type)
  }
  return target.closest("[contenteditable='true'], .cm-editor, [role='textbox'], [role='combobox']") !== null
}

interface ParsedShortcut {
  ctrl: boolean
  shift: boolean
  alt: boolean
  key: string
}

const KEY_ALIASES: Record<string, string> = {
  esc: "escape",
  up: "arrowup",
  down: "arrowdown",
  left: "arrowleft",
  right: "arrowright",
  space: " ",
  return: "enter",
}

function parseShortcut(spec: string): ParsedShortcut {
  const parts = spec
    .toLowerCase()
    .split("+")
    .map((p) => p.trim())
  // “ctrl++” 这类写法不需要，最后一段就是键
  const key = parts.pop() ?? ""
  return {
    ctrl: parts.includes("ctrl") || parts.includes("mod"),
    shift: parts.includes("shift"),
    alt: parts.includes("alt"),
    key: KEY_ALIASES[key] ?? key,
  }
}

/**
 * 判断键盘事件是否匹配快捷键描述，例如 "ctrl+k"、"ctrl+shift+l"、"alt+arrowleft"、"?"、"j"。
 * Ctrl 同时接受 Meta（macOS 的 Command），便于在其他系统上调试。
 */
export function matchShortcut(event: KeyboardEvent, spec: string): boolean {
  const s = parseShortcut(spec)
  const ctrl = event.ctrlKey || event.metaKey
  if (ctrl !== s.ctrl || event.altKey !== s.alt) return false
  const key = event.key.toLowerCase()
  // “?”本身就要按 Shift，不再比较 Shift
  if (s.key === "?") return key === "?"
  if (s.key.length === 1 && !/[a-z0-9]/.test(s.key)) return key === s.key
  if (event.shiftKey !== s.shift) return false
  if (key === s.key) return true
  // 布局差异：按物理键再比较一次字母和数字
  if (s.key.length === 1 && /[a-z0-9]/.test(s.key)) {
    return event.code === `Key${s.key.toUpperCase()}` || event.code === `Digit${s.key}`
  }
  return false
}

const LABELS: Record<string, string> = {
  ctrl: "Ctrl",
  mod: "Ctrl",
  shift: "Shift",
  alt: "Alt",
  enter: "Enter",
  escape: "Esc",
  esc: "Esc",
  arrowup: "↑",
  arrowdown: "↓",
  arrowleft: "←",
  arrowright: "→",
  " ": "空格",
  space: "空格",
  "/": "/",
  "?": "?",
  ",": ",",
}

/** 把快捷键描述拆成键帽文字：["Ctrl", "K"] */
export function shortcutKeys(spec: string): string[] {
  return spec.split("+").map((part) => {
    const p = part.trim().toLowerCase()
    return LABELS[p] ?? (p.length === 1 ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1))
  })
}
