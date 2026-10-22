import { describe, expect, it } from "vitest"
import {
  formatBytes,
  formatCharsArrow,
  formatConfidence,
  formatDuration,
  formatDurationMs,
  formatEta,
  formatNumber,
  formatPercent,
  formatRatio,
  formatRelativeDate,
  formatSecondsRange,
  formatShortMs,
  formatWan,
} from "./format"

describe("千分位", () => {
  it("整数加千分位", () => {
    expect(formatNumber(1284)).toBe("1,284")
    expect(formatNumber(100000)).toBe("100,000")
    expect(formatNumber(5)).toBe("5")
    expect(formatNumber(0)).toBe("0")
  })

  it("小数四舍五入、空值显示破折号", () => {
    expect(formatNumber(1283.6)).toBe("1,284")
    expect(formatNumber(null)).toBe("—")
    expect(formatNumber(undefined)).toBe("—")
    expect(formatNumber(Number.NaN)).toBe("—")
  })

  it("百分比保留一位小数", () => {
    expect(formatPercent(32.14)).toBe("32.1%")
    expect(formatPercent(100)).toBe("100.0%")
  })
})

describe("时长", () => {
  it("秒：13 秒、2 分 13 秒、1 小时 5 分", () => {
    expect(formatDuration(13)).toBe("13 秒")
    expect(formatDuration(133)).toBe("2 分 13 秒")
    expect(formatDuration(120)).toBe("2 分")
    expect(formatDuration(3900)).toBe("1 小时 5 分")
    expect(formatDuration(7200)).toBe("2 小时")
  })

  it("毫秒：820 毫秒、1.2 秒", () => {
    expect(formatDurationMs(820)).toBe("820 毫秒")
    expect(formatDurationMs(1200)).toBe("1.2 秒")
    expect(formatDurationMs(133_000)).toBe("2 分 13 秒")
  })

  it("表格里的短写：820ms、2.1s", () => {
    expect(formatShortMs(820)).toBe("820ms")
    expect(formatShortMs(2100)).toBe("2.1s")
    expect(formatShortMs(65_000)).toBe("1m05s")
  })

  it("预计剩余：约 50 秒、约 3 分钟", () => {
    expect(formatEta(50)).toBe("约 50 秒")
    expect(formatEta(48)).toBe("约 50 秒")
    expect(formatEta(5)).toBe("约 5 秒")
    expect(formatEta(180)).toBe("约 3 分钟")
    expect(formatEta(4800)).toBe("约 1 小时 20 分")
  })

  it("预计耗时区间", () => {
    expect(formatSecondsRange([10, 30])).toBe("10 到 30 秒")
    expect(formatSecondsRange([60, 110])).toBe("1 到 2 分钟")
    expect(formatSecondsRange([20, 20])).toBe("约 20 秒")
  })
})

describe("相对日期", () => {
  const now = new Date(2026, 9, 21, 15, 30) // 2026-10-21 周三

  it("今天显示时刻", () => {
    expect(formatRelativeDate(new Date(2026, 9, 21, 10, 2).toISOString(), now)).toBe("10:02")
  })

  it("昨天显示“昨天”", () => {
    expect(formatRelativeDate(new Date(2026, 9, 20, 23, 59).toISOString(), now)).toBe("昨天")
  })

  it("一周内显示星期", () => {
    expect(formatRelativeDate(new Date(2026, 9, 19, 9, 0).toISOString(), now)).toBe("周一")
    expect(formatRelativeDate(new Date(2026, 9, 18, 9, 0).toISOString(), now)).toBe("周日")
  })

  it("今年更早显示月日，更早显示年月日", () => {
    expect(formatRelativeDate(new Date(2026, 8, 20, 9, 0).toISOString(), now)).toBe("9月20日")
    expect(formatRelativeDate(new Date(2025, 8, 20, 9, 0).toISOString(), now)).toBe("2025年9月20日")
  })

  it("无效时间显示破折号", () => {
    expect(formatRelativeDate(null, now)).toBe("—")
    expect(formatRelativeDate("not a date", now)).toBe("—")
  })
})

describe("压缩比与其他", () => {
  it("倍数用乘号：15×、3.2×", () => {
    expect(formatRatio(15.14)).toBe("15×")
    expect(formatRatio(3.24)).toBe("3.2×")
    expect(formatRatio(2)).toBe("2×")
    expect(formatRatio(null)).toBe("—")
    expect(formatRatio(0)).toBe("—")
  })

  it("字数变化与置信度", () => {
    expect(formatCharsArrow(6240, 412)).toBe("6,240 → 412")
    expect(formatConfidence(0.9)).toBe("0.90")
    expect(formatConfidence(null)).toBe("—")
  })

  it("万与文件大小", () => {
    expect(formatWan(8400)).toBe("8,400")
    expect(formatWan(21_000)).toBe("2.1 万")
    expect(formatWan(30_000)).toBe("3 万")
    expect(formatBytes(512)).toBe("512 B")
    expect(formatBytes(1.2 * 1024 * 1024)).toBe("1.2 MB")
  })
})
