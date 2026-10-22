import { describe, expect, it } from "vitest"
import { createCoalescer, SseParser } from "./sse"

describe("SseParser", () => {
  it("按空行切分事件，读取 event、data、id", () => {
    const parser = new SseParser()
    const out = parser.feed('event: delta\ndata: {"content":"你好"}\nid: 3\n\n')
    expect(out).toEqual([{ event: "delta", data: '{"content":"你好"}', id: "3" }])
  })

  it("跨块拼接、CRLF 换行、多行 data", () => {
    const parser = new SseParser()
    expect(parser.feed("event: done\r\ndata: lin")).toEqual([])
    const out = parser.feed("e1\r\ndata: line2\r\n\r\n")
    expect(out).toEqual([{ event: "done", data: "line1\nline2", id: null }])
  })

  it("忽略注释行，没有 event 时为 message", () => {
    const parser = new SseParser()
    const out = parser.feed(": ping\n\ndata: x\n\n")
    expect(out).toEqual([{ event: "message", data: "x", id: null }])
  })

  it("流结束时派发最后一个没有空行的事件", () => {
    const parser = new SseParser()
    parser.feed("event: error\ndata: {}")
    expect(parser.flush()).toEqual([{ event: "error", data: "{}", id: null }])
  })
})

describe("createCoalescer", () => {
  function setup(minInterval = 100) {
    let clock = 0
    const queue: (() => void)[] = []
    const flushed: { id: number; v: number }[][] = []
    const c = createCoalescer<{ id: number; v: number }, number>({
      key: (x) => x.id,
      onFlush: (items) => flushed.push(items),
      minInterval,
      schedule: (cb) => {
        queue.push(cb)
        return queue.length
      },
      cancelSchedule: () => undefined,
      now: () => clock,
    })
    const frame = (advance = 16) => {
      clock += advance
      const cb = queue.shift()
      cb?.()
    }
    return { c, flushed, frame, queue }
  }

  it("同一条目多次更新只保留最后一次", () => {
    const { c, flushed, frame } = setup()
    c.push([
      { id: 1, v: 1 },
      { id: 2, v: 1 },
    ])
    c.push([{ id: 1, v: 2 }])
    c.push([{ id: 1, v: 3 }])
    frame(200)
    expect(flushed).toHaveLength(1)
    const batch = flushed[0]!
    expect(batch).toHaveLength(2)
    expect(batch.find((x) => x.id === 1)?.v).toBe(3)
  })

  it("两次刷新至少间隔 minInterval（每秒最多 10 次）", () => {
    const { c, flushed, frame } = setup(100)
    c.push([{ id: 1, v: 1 }])
    frame(200)
    expect(flushed).toHaveLength(1)
    c.push([{ id: 1, v: 2 }])
    frame(16) // 距上次刷新 16 ms：不刷新，重新排队
    expect(flushed).toHaveLength(1)
    frame(100)
    expect(flushed).toHaveLength(2)
    expect(flushed[1]![0]!.v).toBe(2)
  })

  it("flushNow 立即刷新，cancel 丢弃缓冲", () => {
    const { c, flushed } = setup()
    c.push([{ id: 7, v: 1 }])
    c.flushNow()
    expect(flushed).toHaveLength(1)
    c.push([{ id: 8, v: 1 }])
    c.cancel()
    expect(c.size).toBe(0)
  })
})
