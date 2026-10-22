/**
 * 线网图的几何计算（06 第 5.1 节 LineMap），全部是纯函数，便于单元测试。
 *
 * - 线路按条数从多到少、从上到下排列；color_index = -1 的意图合并成一条灰色“其他 N 类”，放在最后；
 * - 线宽 3 + 9 × sqrt(count / 最大 count)，范围 3–12；
 * - 所有线路从枢纽出发时上下并排成一束（线间留 2 px），并排水平走一段（约为枢纽到终点距离的三分之一，
 *   至少 64 px）后以 45° 转向自己终点站的高度，再水平走到终点；并排顺序与终点顺序一致，线路之间不会交叉；
 * - 外侧的线先转、内侧的线依次晚 14 px 转（失败线在最下面，是向下一组里最外侧的一条），斜线段之间也留有间隙；
 * - 转角用 10 px 圆角，斜线太短时缩小；
 * - 行距 clamp((高度 − 上下边距) / 线路数, 34, 64)；
 * - 每条路径的命令结构完全相同（M H Q L Q H），CSS 的 d 属性过渡才能平滑变形。
 */

export interface CategoryInput {
  label: string
  count: number
  percent: number
  color_index: number
}

export interface MapLineSpec {
  key: string
  label: string
  count: number
  percent: number
  colorIndex: number
  /** 合并进“其他”的意图名 */
  members: string[]
}

export interface MapLine extends MapLineSpec {
  width: number
  bundleY: number
  endY: number
  turnX: number
  path: string
  stationR: number
}

export interface LineMapLayout {
  width: number
  height: number
  rowHeight: number
  hub: { x: number; y: number; width: number; height: number }
  terminalX: number
  lines: MapLine[]
  failed: { count: number; path: string; endY: number; bundleY: number; turnX: number; stationR: number } | null
  /** 运行中、还没有结果时的占位虚线 */
  emptyPath: string | null
  emptyY: number
}

export const GEOMETRY = {
  padTop: 40,
  padBottom: 16,
  hubX: 16,
  hubWidth: 28,
  /** 并排段的最短长度 */
  minRun: 64,
  /** 并排段约为枢纽到终点距离的三分之一 */
  runRatio: 1 / 3,
  labelWidth: 260,
  corner: 10,
  bundleGap: 2,
  /** 外侧的线先转，往里每条晚 14 px 转 */
  stagger: 14,
  minRow: 34,
  maxRow: 64,
  maxColored: 11,
  failedWidth: 3,
} as const

export const OTHER_KEY = "__other__"

/** 线宽：3 + 9 × sqrt(count / maxCount)，限制在 3–12 */
export function lineWidth(count: number, maxCount: number): number {
  if (maxCount <= 0 || count <= 0) return 3
  const w = 3 + 9 * Math.sqrt(count / maxCount)
  return Math.min(12, Math.max(3, w))
}

/** 行距：clamp((高度 − 上下边距) / 线路数, 34, 64) */
export function rowHeight(height: number, padding: number, rows: number): number {
  if (rows <= 0) return GEOMETRY.maxRow
  const raw = (height - padding) / rows
  return Math.min(GEOMETRY.maxRow, Math.max(GEOMETRY.minRow, raw))
}

/** 终点站半径：max(6, 线宽 / 2 + 3) */
export function stationRadius(width: number): number {
  return Math.max(6, width / 2 + 3)
}

/**
 * 把类别统计整理成线路：彩色线路（color_index 0–10）按条数从多到少，最多 11 条；
 * color_index = -1（以及超出 11 条的部分）合并成一条“其他 N 类”放在最后。
 */
export function buildLines(categories: readonly CategoryInput[], maxColored: number = GEOMETRY.maxColored): MapLineSpec[] {
  const sorted = [...categories].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
  const colored: MapLineSpec[] = []
  const others: CategoryInput[] = []
  for (const c of sorted) {
    if (c.color_index >= 0 && c.color_index <= 10 && colored.length < maxColored) {
      colored.push({
        key: c.label,
        label: c.label,
        count: c.count,
        percent: c.percent,
        colorIndex: c.color_index,
        members: [c.label],
      })
    } else {
      others.push(c)
    }
  }
  if (others.length > 0) {
    colored.push({
      key: OTHER_KEY,
      label: `其他 ${others.length} 类`,
      count: others.reduce((s, c) => s + c.count, 0),
      percent: Math.round(others.reduce((s, c) => s + c.percent, 0) * 10) / 10,
      colorIndex: -1,
      members: others.map((c) => c.label),
    })
  }
  return colored
}

/**
 * 按给定的键顺序排列线路（运行中最多每 2 秒重排一次，期间保持旧顺序，新线路追加在末尾）。
 * “其他”始终在最后。
 */
export function orderLines(lines: readonly MapLineSpec[], order: readonly string[] | null): MapLineSpec[] {
  if (!order) return [...lines]
  const rank = new Map(order.map((k, i) => [k, i]))
  const known = lines.filter((l) => rank.has(l.key) && l.key !== OTHER_KEY)
  const fresh = lines.filter((l) => !rank.has(l.key) && l.key !== OTHER_KEY)
  const other = lines.filter((l) => l.key === OTHER_KEY)
  known.sort((a, b) => (rank.get(a.key) ?? 0) - (rank.get(b.key) ?? 0))
  return [...known, ...fresh, ...other]
}

function r1(n: number): number {
  return Math.round(n * 10) / 10
}

/**
 * 一条线路的路径：从 (x0, y0) 水平到 turnX，45° 转向 y1，再水平到 xEnd。
 * dx 不够 45° 时（容器太窄）退化为更陡的斜线。
 */
export function linePath(x0: number, y0: number, turnX: number, y1: number, xEnd: number, maxDiagonalDx: number): string {
  const dy = y1 - y0
  const ady = Math.abs(dy)
  const dx = Math.min(ady, Math.max(0, maxDiagonalDx))
  const p1x = turnX
  const p1y = y0
  const p2x = turnX + dx
  const p2y = y1
  const len = Math.hypot(dx, dy)
  if (len < 0.5) {
    // 直线：保持相同的命令结构
    const y = y0
    return `M${r1(x0)} ${r1(y)}H${r1(p1x)}Q${r1(p1x)} ${r1(y)} ${r1(p1x)} ${r1(y)}L${r1(p1x)} ${r1(y)}Q${r1(p1x)} ${r1(y)} ${r1(p1x)} ${r1(y)}H${r1(xEnd)}`
  }
  const ux = dx / len
  const uy = dy / len
  const c = Math.min(GEOMETRY.corner, len / 2, Math.max(0, p1x - x0), Math.max(0, xEnd - p2x))
  const ax = p1x - c
  const bx = p1x + ux * c
  const by = p1y + uy * c
  const cx = p2x - ux * c
  const cy = p2y - uy * c
  const dxEnd = p2x + c
  return `M${r1(x0)} ${r1(y0)}H${r1(ax)}Q${r1(p1x)} ${r1(p1y)} ${r1(bx)} ${r1(by)}L${r1(cx)} ${r1(cy)}Q${r1(p2x)} ${r1(p2y)} ${r1(dxEnd)} ${r1(p2y)}H${r1(xEnd)}`
}

/** 并排段的长度：枢纽右缘到终点距离的三分之一，至少 64 px */
export function bundleRun(x0: number, terminalX: number): number {
  return Math.max(GEOMETRY.minRun, (terminalX - x0) * GEOMETRY.runRatio)
}

/**
 * 每条线开始转弯的横坐标。向下转的线从束里最靠下（最外侧）的一条开始，向上转的从最靠上的一条开始，
 * 外侧的先转，往里每条晚 stagger px；不需要转弯的线取 base。
 */
export function turnPositions(
  bundleYs: readonly number[],
  endYs: readonly number[],
  base: number,
  stagger: number = GEOMETRY.stagger,
): number[] {
  const turns = bundleYs.map(() => base)
  const indexes = bundleYs.map((_, i) => i)
  const delta = (i: number) => (endYs[i] as number) - (bundleYs[i] as number)
  const down = indexes.filter((i) => delta(i) > 0.5).sort((a, b) => (bundleYs[b] as number) - (bundleYs[a] as number))
  const up = indexes.filter((i) => delta(i) < -0.5).sort((a, b) => (bundleYs[a] as number) - (bundleYs[b] as number))
  down.forEach((idx, k) => {
    turns[idx] = base + k * stagger
  })
  up.forEach((idx, k) => {
    turns[idx] = base + k * stagger
  })
  return turns
}

export interface LayoutInput {
  lines: readonly MapLineSpec[]
  failed: number
  width: number
  height: number
}

export function layoutLineMap(input: LayoutInput): LineMapLayout {
  const g = GEOMETRY
  const width = Math.max(input.width, 360)
  const lines = input.lines
  const hasFailed = input.failed > 0
  const rows = lines.length + (hasFailed ? 1 : 0)
  const rowH = rowHeight(input.height, g.padTop + g.padBottom, Math.max(1, rows))
  const height = g.padTop + g.padBottom + rowH * Math.max(1, rows)
  const terminalX = width - g.labelWidth
  const x0 = g.hubX + g.hubWidth

  const maxCount = lines.reduce((m, l) => Math.max(m, l.count), 0)
  const widths = lines.map((l) => lineWidth(l.count, maxCount))

  // 并排成一束：总高度 = 各线宽 + 间隔；以绘图区中线为中心
  let bundleHeight = widths.reduce((s, w) => s + w, 0) + g.bundleGap * Math.max(0, lines.length - 1)
  if (hasFailed) bundleHeight += (lines.length > 0 ? g.bundleGap : 0) + g.failedWidth
  const centerY = g.padTop + (rowH * Math.max(1, rows)) / 2
  let cursor = centerY - bundleHeight / 2
  const bundleYs: number[] = []
  for (const w of widths) {
    bundleYs.push(cursor + w / 2)
    cursor += w + g.bundleGap
  }
  const failedBundleY = cursor + g.failedWidth / 2

  const hubPad = 8
  const hub = {
    x: g.hubX,
    y: Math.min(centerY - 20, centerY - bundleHeight / 2 - hubPad),
    width: g.hubWidth,
    height: Math.max(40, bundleHeight + hubPad * 2),
  }

  const endYs = lines.map((_, i) => g.padTop + rowH * (i + 0.5))
  const failedEndY = g.padTop + rowH * (lines.length + 0.5)

  // 失败线和彩色线一起排转弯顺序：外侧的先转，内侧的依次晚 14 px
  const base = x0 + bundleRun(x0, terminalX)
  const turnXs = turnPositions(
    hasFailed ? [...bundleYs, failedBundleY] : bundleYs,
    hasFailed ? [...endYs, failedEndY] : endYs,
    base,
  )

  const mapLines: MapLine[] = lines.map((l, i) => {
    const w = widths[i] as number
    const by = bundleYs[i] as number
    const ey = endYs[i] as number
    const tx = turnXs[i] as number
    const maxDx = terminalX - tx - 24
    return {
      ...l,
      width: w,
      bundleY: by,
      endY: ey,
      turnX: tx,
      path: linePath(x0, by, tx, ey, terminalX, maxDx),
      stationR: stationRadius(w),
    }
  })

  let failed: LineMapLayout["failed"] = null
  if (hasFailed) {
    const tx = turnXs[lines.length] as number
    failed = {
      count: input.failed,
      bundleY: failedBundleY,
      endY: failedEndY,
      turnX: tx,
      path: linePath(x0, failedBundleY, tx, failedEndY, terminalX, terminalX - tx - 24),
      stationR: 6,
    }
  }

  const emptyY = g.padTop + rowH / 2
  const emptyPath = rows === 0 ? `M${x0} ${r1(centerY)}H${r1(terminalX)}` : null

  return {
    width,
    height,
    rowHeight: rowH,
    hub: rows === 0 ? { x: g.hubX, y: centerY - 20, width: g.hubWidth, height: 40 } : hub,
    terminalX,
    lines: mapLines,
    failed,
    emptyPath,
    emptyY: rows === 0 ? centerY : emptyY,
  }
}

/** 线网图的文字替代：“共 1,284 条，5 个意图，最多的是物流查询 412 条” */
export function describeLineMap(total: number, lines: readonly MapLineSpec[], failed: number, format: (n: number) => string): string {
  const intents = lines.reduce((s, l) => s + l.members.length, 0)
  if (lines.length === 0) return failed > 0 ? `共 ${format(total)} 条，${format(failed)} 条失败，还没有识别结果` : "还没有识别结果"
  const top = [...lines].sort((a, b) => b.count - a.count)[0] as MapLineSpec
  const failedText = failed > 0 ? `，${format(failed)} 条失败` : ""
  return `共 ${format(total)} 条，${intents} 个意图，最多的是${top.label} ${format(top.count)} 条${failedText}`
}
