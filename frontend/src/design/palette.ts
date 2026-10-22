/**
 * 线路色分配和对比度规则（06 第 3.3 节）。
 * 颜色值与 tokens.css 一致；这里保留一份十六进制值，只用来按 WCAG 计算对比度，
 * 组件里实际着色仍然引用 CSS 变量（var(--line-N)），主题切换时自动生效。
 */

export type ThemeName = "light" | "dark"

/** 彩色线路的数量（序号 0–10） */
export const LINE_COUNT = 11

export const LINE_NAMES = ["蓝", "绿", "黄", "紫", "青", "橙", "玫红", "棕", "橄榄", "靛", "红"] as const

export const LINE_COLORS: Record<ThemeName, readonly string[]> = {
  light: [
    "#0B6FD6",
    "#2DBE6C",
    "#F2A900",
    "#7B5CD6",
    "#0EA5A4",
    "#F2711C",
    "#C2368F",
    "#8C6D46",
    "#4E7D22",
    "#2F4FA2",
    "#C23B3B",
  ],
  dark: [
    "#4C9BFF",
    "#3CCB7F",
    "#FFC53D",
    "#A08BFF",
    "#2ED3C6",
    "#FF8F4C",
    "#F06CC0",
    "#C49A6C",
    "#8CC152",
    "#6F8CFF",
    "#FF6B6B",
  ],
}

export const OTHER_COLOR: Record<ThemeName, string> = { light: "#9AA5B1", dark: "#7A8796" }

/** 线条所在面板的底色（线网图画在 --surface 上） */
export const SURFACE_COLOR: Record<ThemeName, string> = { light: "#FFFFFF", dark: "#152436" }

/** 徽标文字的两种候选：白字，或本主题的墨色字（亮色 #1E2B38、暗色 #0F1B2A），与 tokens.css 的 --badge-* 一致 */
export const BADGE_WHITE = "#FFFFFF"
export const BADGE_INK: Record<ThemeName, string> = { light: "#1E2B38", dark: "#0F1B2A" }

/** 序号是否落在“其他”灰：-1、超出 0–10 或不是整数 */
export function isOtherIndex(index: number): boolean {
  return !Number.isInteger(index) || index < 0 || index >= LINE_COUNT
}

/** 序号对应的十六进制颜色 */
export function lineColor(index: number, theme: ThemeName): string {
  if (isOtherIndex(index)) return OTHER_COLOR[theme]
  return LINE_COLORS[theme][index] as string
}

/** 序号对应的 CSS 变量，组件着色用它 */
export function lineVar(index: number): string {
  return isOtherIndex(index) ? "var(--line-other)" : `var(--line-${index})`
}

function hexToRgb(hex: string): [number, number, number] {
  let h = hex.trim().replace(/^#/, "")
  if (h.length === 3) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("")
  }
  if (!/^[0-9a-fA-F]{6}$/.test(h)) throw new Error(`不是有效的颜色：${hex}`)
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

/** WCAG 2.x 相对亮度 */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** 两种颜色的对比度，1–21 */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a)
  const lb = relativeLuminance(b)
  const hi = Math.max(la, lb)
  const lo = Math.min(la, lb)
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * 徽标文字：分别计算白字和本主题墨色字与底色的对比度，取较高的那个（06 第 3.3 节）。
 * 线路色已经调过，保证至少一种 ≥ 4.5：亮色主题下绿、黄、青、橙、灰用墨色字，其余用白字；暗色主题下全部用墨色字。
 */
export function badgeTextColor(background: string, theme: ThemeName): string {
  const ink = BADGE_INK[theme]
  return contrastRatio(BADGE_WHITE, background) >= contrastRatio(ink, background) ? BADGE_WHITE : ink
}

/** 线条与背景的对比度低于 3 时需要 1 px 描边 */
export function needsStroke(color: string, background: string): boolean {
  return contrastRatio(color, background) < 3
}

/** 描边色：线路色与黑色按 65 : 35 混合 */
export function strokeMix(colorCss: string): string {
  return `color-mix(in oklab, ${colorCss} 65%, black)`
}

/** 暗色主题下线网图的线路微光（只有线网图使用） */
export function glowFilter(colorCss: string): string {
  return `drop-shadow(0 0 4px color-mix(in srgb, ${colorCss} 45%, transparent))`
}

export interface LineStyle {
  /** 线条和徽标底色（CSS 变量） */
  color: string
  /** 徽标文字颜色（CSS 变量） */
  text: string
  /** 需要描边时的描边色，否则为 null */
  stroke: string | null
  /** 是否是“其他”灰 */
  other: boolean
}

/** 某个线路序号在当前主题下的完整样式 */
export function lineStyle(index: number, theme: ThemeName): LineStyle {
  const hex = lineColor(index, theme)
  const color = lineVar(index)
  const text = badgeTextColor(hex, theme) === BADGE_WHITE ? "var(--badge-white)" : "var(--badge-ink)"
  const stroke = needsStroke(hex, SURFACE_COLOR[theme]) ? strokeMix(color) : null
  return { color, text, stroke, other: isOtherIndex(index) }
}
