import { describe, expect, it } from "vitest"
import {
  buildLines,
  bundleRun,
  describeLineMap,
  GEOMETRY,
  layoutLineMap,
  linePath,
  lineWidth,
  orderLines,
  OTHER_KEY,
  rowHeight,
  stationRadius,
  turnPositions,
  type CategoryInput,
} from "./lineMapGeometry"

function cats(counts: number[], colors?: number[]): CategoryInput[] {
  const total = counts.reduce((s, c) => s + c, 0)
  return counts.map((count, i) => ({
    label: `意图${i + 1}`,
    count,
    percent: Math.round((count / total) * 1000) / 10,
    color_index: colors ? (colors[i] as number) : i,
  }))
}

describe("线宽与行距", () => {
  it("线宽 3 + 9 × sqrt(count / 最大 count)，范围 3–12", () => {
    expect(lineWidth(100, 100)).toBe(12)
    expect(lineWidth(25, 100)).toBeCloseTo(3 + 9 * 0.5, 5)
    expect(lineWidth(0, 100)).toBe(3)
    expect(lineWidth(1, 1_000_000)).toBeGreaterThanOrEqual(3)
    for (const c of [1, 7, 50, 99, 100]) {
      const w = lineWidth(c, 100)
      expect(w).toBeGreaterThanOrEqual(3)
      expect(w).toBeLessThanOrEqual(12)
    }
  })

  it("行距 clamp((高度 − 上下边距) / 线路数, 34, 64)", () => {
    expect(rowHeight(1000, 56, 5)).toBe(64)
    expect(rowHeight(300, 56, 12)).toBe(34)
    expect(rowHeight(456, 56, 8)).toBe(50)
  })

  it("终点站半径 max(6, 线宽 / 2 + 3)", () => {
    expect(stationRadius(3)).toBe(6)
    expect(stationRadius(12)).toBe(9)
  })
})

describe("线路整理", () => {
  it("按条数从多到少排列", () => {
    const lines = buildLines(cats([5, 50, 20], [0, 1, 2]))
    expect(lines.map((l) => l.count)).toEqual([50, 20, 5])
  })

  it("color_index = -1 的意图合并成“其他 N 类”，放在最后", () => {
    const input = cats([100, 90, 80, 3, 2], [0, 1, 2, -1, -1])
    const lines = buildLines(input)
    expect(lines).toHaveLength(4)
    const other = lines[lines.length - 1]
    expect(other?.key).toBe(OTHER_KEY)
    expect(other?.label).toBe("其他 2 类")
    expect(other?.count).toBe(5)
    expect(other?.members).toEqual(["意图4", "意图5"])
  })

  it("最多 11 条彩色线路", () => {
    const counts = Array.from({ length: 15 }, (_, i) => 200 - i)
    const colors = counts.map((_, i) => (i < 11 ? i : -1))
    const lines = buildLines(cats(counts, colors))
    expect(lines.filter((l) => l.key !== OTHER_KEY)).toHaveLength(11)
    expect(lines.find((l) => l.key === OTHER_KEY)?.members).toHaveLength(4)
  })

  it("运行中保持旧顺序，新线路追加在末尾，“其他”始终最后", () => {
    const lines = buildLines(cats([10, 30, 20, 1], [0, 1, 2, -1]))
    const ordered = orderLines(lines, ["意图1", "意图3"])
    expect(ordered.map((l) => l.key)).toEqual(["意图1", "意图3", "意图2", OTHER_KEY])
  })
})

describe("布局", () => {
  it("终点顺序与并排顺序一致（线路不交叉）", () => {
    const lines = buildLines(cats([412, 388, 251, 147, 86, 40, 12]))
    const layout = layoutLineMap({ lines, failed: 12, width: 900, height: 480 })
    for (let i = 1; i < layout.lines.length; i++) {
      const prev = layout.lines[i - 1]
      const cur = layout.lines[i]
      expect(cur!.bundleY).toBeGreaterThan(prev!.bundleY)
      expect(cur!.endY).toBeGreaterThan(prev!.endY)
    }
    // 束内相邻线之间至少留 2 px
    for (let i = 1; i < layout.lines.length; i++) {
      const prev = layout.lines[i - 1]!
      const cur = layout.lines[i]!
      expect(cur.bundleY - cur.width / 2 - (prev.bundleY + prev.width / 2)).toBeGreaterThanOrEqual(GEOMETRY.bundleGap - 0.01)
    }
    // 失败线在最下面
    expect(layout.failed).not.toBeNull()
    expect(layout.failed!.endY).toBeGreaterThan(layout.lines[layout.lines.length - 1]!.endY)
  })

  it("并排段约为枢纽到终点距离的三分之一，至少 64 px", () => {
    expect(bundleRun(44, 644)).toBeCloseTo(200, 5)
    expect(bundleRun(44, 160)).toBe(GEOMETRY.minRun)
    const layout = layoutLineMap({ lines: buildLines(cats([50, 40, 30])), failed: 0, width: 1000, height: 400 })
    const x0 = GEOMETRY.hubX + GEOMETRY.hubWidth
    const first = Math.min(...layout.lines.map((l) => l.turnX))
    expect(first).toBeCloseTo(x0 + (layout.terminalX - x0) / 3, 5)
  })

  it("外侧的线先转，内侧的线依次晚 14 px 转", () => {
    // 束内从上到下 0–4；终点更分散：0、1 向上转，3、4 向下转，2 基本水平
    const turns = turnPositions([100, 110, 120, 130, 140], [40, 80, 120, 160, 200], 200)
    expect(turns).toEqual([200, 214, 200, 214, 200])
  })

  it("失败线是向下转的一组里最外侧的一条，最先转", () => {
    const lines = buildLines(cats([412, 388, 251, 147, 86]))
    const layout = layoutLineMap({ lines, failed: 12, width: 1000, height: 480 })
    const downTurns = layout.lines.filter((l) => l.endY - l.bundleY > 0.5).map((l) => l.turnX)
    expect(layout.failed!.turnX).toBeLessThan(Math.min(...downTurns))
  })

  it("同方向相邻两条线的斜线段之间留有间隙", () => {
    const lines = buildLines(cats([412, 388, 251, 147, 86, 40, 12]))
    const layout = layoutLineMap({ lines, failed: 0, width: 1100, height: 520 })
    const all = layout.lines
    for (let i = 1; i < all.length; i++) {
      const a = all[i - 1]!
      const b = all[i]!
      const da = a.endY - a.bundleY
      const db = b.endY - b.bundleY
      if (da > 0.5 && db > 0.5) {
        // 都向下：b 在外侧（更靠下）先转。同一横坐标上两条斜线的竖直距离换算成垂直距离
        const offset = b.bundleY - a.bundleY + (a.turnX - b.turnX)
        expect(offset / Math.SQRT2).toBeGreaterThanOrEqual((a.width + b.width) / 2)
      } else if (da < -0.5 && db < -0.5) {
        // 都向上：a 在外侧（更靠上）先转
        const offset = b.bundleY - a.bundleY + (b.turnX - a.turnX)
        expect(offset / Math.SQRT2).toBeGreaterThanOrEqual((a.width + b.width) / 2)
      }
    }
  })

  it("转角用 10 px 圆角", () => {
    expect(GEOMETRY.corner).toBe(10)
    // 起点 (44,100) 水平到 200，再 45° 向下：第一个圆角从 x = 190 开始
    expect(linePath(44, 100, 200, 200, 640, 400).startsWith("M44 100H190Q200 100")).toBe(true)
  })

  it("右侧留 260 px 放终点站标签", () => {
    const layout = layoutLineMap({ lines: buildLines(cats([3, 2])), failed: 0, width: 800, height: 300 })
    expect(layout.terminalX).toBe(800 - GEOMETRY.labelWidth)
  })

  it("每条路径的命令结构相同（便于 d 属性过渡）", () => {
    const structure = (d: string) => d.replace(/[^A-Za-z]/g, "")
    const lines = buildLines(cats([50, 40, 30]))
    const layout = layoutLineMap({ lines, failed: 0, width: 900, height: 400 })
    const shapes = new Set(layout.lines.map((l) => structure(l.path)))
    expect(shapes.size).toBe(1)
    expect([...shapes][0]).toBe("MHQLQH")
    expect(structure(linePath(44, 100, 108, 100, 640, 400))).toBe("MHQLQH")
  })

  it("没有结果时只画枢纽和一条虚线", () => {
    const layout = layoutLineMap({ lines: [], failed: 0, width: 800, height: 300 })
    expect(layout.lines).toHaveLength(0)
    expect(layout.emptyPath).not.toBeNull()
  })

  it("文字替代概括线网图", () => {
    const lines = buildLines(cats([412, 388, 251, 147, 86]))
    const text = describeLineMap(1284, lines, 0, (n) => n.toLocaleString("en-US"))
    expect(text).toBe("共 1,284 条，5 个意图，最多的是意图1 412 条")
  })
})
