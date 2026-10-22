import { describe, expect, it } from "vitest"
import {
  BADGE_INK,
  BADGE_WHITE,
  badgeTextColor,
  contrastRatio,
  isOtherIndex,
  LINE_COLORS,
  lineColor,
  lineStyle,
  lineVar,
  needsStroke,
  OTHER_COLOR,
  relativeLuminance,
  SURFACE_COLOR,
} from "./palette"

describe("线路色分配", () => {
  it("序号 0–10 对应 06 第 3.3 节的线路色", () => {
    expect(lineColor(0, "light")).toBe("#0B6FD6")
    expect(lineColor(1, "light")).toBe("#2DBE6C")
    expect(lineColor(6, "light")).toBe("#C2368F")
    expect(lineColor(8, "light")).toBe("#4E7D22")
    expect(lineColor(10, "light")).toBe("#C23B3B")
    expect(lineColor(0, "dark")).toBe("#4C9BFF")
    expect(lineColor(10, "dark")).toBe("#FF6B6B")
    expect(LINE_COLORS.light).toHaveLength(11)
    expect(LINE_COLORS.dark).toHaveLength(11)
  })

  it("-1 和超出范围的序号落到“其他”灰", () => {
    expect(isOtherIndex(-1)).toBe(true)
    expect(isOtherIndex(11)).toBe(true)
    expect(isOtherIndex(1.5)).toBe(true)
    expect(isOtherIndex(0)).toBe(false)
    expect(lineColor(-1, "light")).toBe(OTHER_COLOR.light)
    expect(lineColor(-1, "dark")).toBe(OTHER_COLOR.dark)
    expect(lineColor(99, "light")).toBe(OTHER_COLOR.light)
  })

  it("组件着色用 CSS 变量", () => {
    expect(lineVar(3)).toBe("var(--line-3)")
    expect(lineVar(-1)).toBe("var(--line-other)")
  })
})

describe("对比度", () => {
  it("相对亮度和对比度符合 WCAG 公式", () => {
    expect(relativeLuminance("#FFFFFF")).toBeCloseTo(1, 5)
    expect(relativeLuminance("#000000")).toBeCloseTo(0, 5)
    expect(contrastRatio("#FFFFFF", "#000000")).toBeCloseTo(21, 1)
    expect(contrastRatio("#777777", "#777777")).toBeCloseTo(1, 5)
    expect(contrastRatio("#FFF", "#000")).toBeCloseTo(21, 1)
  })

  it("徽标文字：白字和本主题墨色字取对比度较高的那个", () => {
    // 亮色主题：绿、黄、青、橙、灰用墨色字，其余用白字（06 第 3.3 节）
    const inkLight = [1, 2, 4, 5]
    for (let i = 0; i < LINE_COLORS.light.length; i++) {
      const expected = inkLight.includes(i) ? BADGE_INK.light : BADGE_WHITE
      expect(badgeTextColor(lineColor(i, "light"), "light"), `线路色 ${i}`).toBe(expected)
    }
    expect(badgeTextColor(OTHER_COLOR.light, "light")).toBe(BADGE_INK.light)
    // 暗色主题的线路色都偏亮，全部用暗色主题的墨色字
    for (const color of [...LINE_COLORS.dark, OTHER_COLOR.dark]) expect(badgeTextColor(color, "dark")).toBe(BADGE_INK.dark)
  })

  it("每种线路色至少有一种徽标文字的对比度 ≥ 4.5", () => {
    for (const theme of ["light", "dark"] as const) {
      for (const color of [...LINE_COLORS[theme], OTHER_COLOR[theme]]) {
        const best = Math.max(contrastRatio(BADGE_WHITE, color), contrastRatio(BADGE_INK[theme], color))
        expect(best, `${theme} ${color}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it("线条与背景的对比度低于 3 时需要描边", () => {
    expect(needsStroke(lineColor(1, "light"), SURFACE_COLOR.light)).toBe(true) // 绿
    expect(needsStroke(lineColor(2, "light"), SURFACE_COLOR.light)).toBe(true) // 黄
    expect(needsStroke(lineColor(5, "light"), SURFACE_COLOR.light)).toBe(true) // 橙
    expect(needsStroke(OTHER_COLOR.light, SURFACE_COLOR.light)).toBe(true) // 灰
    expect(needsStroke(lineColor(0, "light"), SURFACE_COLOR.light)).toBe(false) // 蓝
    for (const color of LINE_COLORS.dark) expect(needsStroke(color, SURFACE_COLOR.dark)).toBe(false)
  })

  it("lineStyle 组合出颜色、文字和描边", () => {
    const yellow = lineStyle(2, "light")
    expect(yellow.color).toBe("var(--line-2)")
    expect(yellow.text).toBe("var(--badge-ink)")
    expect(yellow.stroke).toBe("color-mix(in oklab, var(--line-2) 65%, black)")
    const blue = lineStyle(0, "light")
    expect(blue.text).toBe("var(--badge-white)")
    expect(blue.stroke).toBeNull()
    expect(lineStyle(0, "dark").text).toBe("var(--badge-ink)")
    expect(lineStyle(-1, "dark").other).toBe(true)
  })
})
