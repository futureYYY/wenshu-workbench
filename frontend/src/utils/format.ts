/** 数字、时长、日期的显示格式（06 第 9 节“数字和单位”“日期”）。 */

const numberFormat = new Intl.NumberFormat("en-US")

/** 千分位：1,284 */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  return numberFormat.format(Math.round(value))
}

/** 百分比保留一位小数：32.1% */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  return `${value.toFixed(digits)}%`
}

/** 时长（秒）：13 秒、2 分 13 秒、1 小时 5 分 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—"
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} 秒`
  if (s < 3600) {
    const m = Math.floor(s / 60)
    const r = s % 60
    return r ? `${m} 分 ${r} 秒` : `${m} 分`
  }
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`
}

/** 正文里的耗时（毫秒）：820 毫秒、1.2 秒、2 分 13 秒 */
export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—"
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} 毫秒`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} 秒`
  return formatDuration(ms / 1000)
}

/** 表格和导视数字里的短写：820ms、2.1s、3m05s */
export function formatShortMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—"
  if (ms < 1000) return `${Math.max(0, Math.round(ms))}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}m${String(s).padStart(2, "0")}s`
}

/** 预计剩余时间：约 50 秒、约 3 分钟、约 1 小时 20 分 */
export function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—"
  const s = Math.max(0, Math.round(seconds))
  if (s < 10) return `约 ${Math.max(1, s)} 秒`
  if (s < 60) return `约 ${Math.max(10, Math.round(s / 5) * 5)} 秒`
  if (s < 3600) return `约 ${Math.max(1, Math.round(s / 60))} 分钟`
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return m ? `约 ${h} 小时 ${m} 分` : `约 ${h} 小时`
}

/** 预计耗时区间：10 到 30 秒、1 到 2 分钟 */
export function formatSecondsRange(range: readonly [number, number] | null | undefined): string {
  if (!range) return "—"
  const lo = Math.max(0, Math.min(range[0], range[1]))
  const hi = Math.max(range[0], range[1])
  if (hi < 60) {
    const a = Math.max(1, Math.round(lo))
    const b = Math.max(a, Math.round(hi))
    return a === b ? `约 ${a} 秒` : `${a} 到 ${b} 秒`
  }
  if (hi < 3600) {
    const a = Math.max(1, Math.round(lo / 60))
    const b = Math.max(a, Math.ceil(hi / 60))
    return a === b ? `约 ${a} 分钟` : `${a} 到 ${b} 分钟`
  }
  const a = Math.max(1, Math.round(lo / 3600))
  const b = Math.max(a, Math.ceil(hi / 3600))
  return a === b ? `约 ${a} 小时` : `${a} 到 ${b} 小时`
}

/** 大数用“万”：8,400、2.1 万 */
export function formatWan(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  if (Math.abs(value) < 10_000) return formatNumber(value)
  const wan = value / 10_000
  const text = wan >= 100 ? String(Math.round(wan)) : wan.toFixed(1).replace(/\.0$/, "")
  return `${text} 万`
}

/** 压缩比：15×、3.2× */
export function formatRatio(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio) || ratio <= 0) return "—"
  if (ratio >= 10) return `${Math.round(ratio)}×`
  return `${ratio.toFixed(1).replace(/\.0$/, "")}×`
}

/** 文件大小：820 B、12.4 KB、1.2 MB */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 字数变化：6,240 → 412 */
export function formatCharsArrow(input: number | null | undefined, output: number | null | undefined): string {
  return `${formatNumber(input)} → ${formatNumber(output)}`
}

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

function pad2(n: number): string {
  return String(n).padStart(2, "0")
}

/** 相对日期：今天 10:02、昨天、周一、9月20日、2025年9月20日 */
export function formatRelativeDate(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000)
  if (days <= 0) return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  if (days === 1) return "昨天"
  if (days < 7) return WEEKDAYS[d.getDay()] as string
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日`
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

/** 完整的本地时间：2026-10-21 14:05 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** 两个时间点之间的秒数 */
export function secondsBetween(startIso: string | null | undefined, endIso?: string | null): number | null {
  if (!startIso) return null
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end)) return null
  return Math.max(0, (end - start) / 1000)
}

/** 置信度两位小数 */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  return value.toFixed(2)
}
