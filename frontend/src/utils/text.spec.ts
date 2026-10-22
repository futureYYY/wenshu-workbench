import { describe, expect, it } from "vitest"
import { matchShortcut, shortcutKeys } from "./keyboard"
import { estimateTokens, extractOmittedChars, filenameFromDisposition, fuzzyScore, listVariables } from "./text"

describe("文本工具", () => {
  it("tokens 估算与后端公式一致：中文每字 1，其余每 3.5 字 1", () => {
    expect(estimateTokens("")).toBe(0)
    expect(estimateTokens("你好世界")).toBe(4)
    expect(estimateTokens("abcdefg")).toBe(2)
    expect(estimateTokens("你好abc")).toBe(3)
  })

  it("从截断后的发送内容里取省略字数", () => {
    expect(extractOmittedChars("前面\n……（中间省略 3210 字）……\n后面")).toBe(3210)
    expect(extractOmittedChars("没有截断")).toBeNull()
  })

  it("从 Content-Disposition 取文件名", () => {
    const name = "客服对话_意图识别_20261021-1405.xlsx"
    expect(filenameFromDisposition(`attachment; filename*=UTF-8''${encodeURIComponent(name)}`)).toBe(name)
    expect(filenameFromDisposition('attachment; filename="a.csv"')).toBe("a.csv")
    expect(filenameFromDisposition(null)).toBeNull()
  })

  it("列出模板里的变量", () => {
    expect(listVariables("{{text}} {{ col:客户等级 }} {{text}} {{foo}}")).toEqual(["text", "col:客户等级", "foo"])
  })

  it("模糊匹配：直接包含得分最高，不匹配为 -1", () => {
    expect(fuzzyScore("意图", "默认意图识别")).toBeGreaterThan(fuzzyScore("默识", "默认意图识别"))
    expect(fuzzyScore("xyz", "默认意图识别")).toBe(-1)
  })
})

describe("快捷键", () => {
  function key(init: KeyboardEventInit) {
    return new KeyboardEvent("keydown", init)
  }

  it("匹配组合键", () => {
    expect(matchShortcut(key({ key: "k", ctrlKey: true }), "ctrl+k")).toBe(true)
    expect(matchShortcut(key({ key: "L", ctrlKey: true, shiftKey: true }), "ctrl+shift+l")).toBe(true)
    expect(matchShortcut(key({ key: "k" }), "ctrl+k")).toBe(false)
    expect(matchShortcut(key({ key: "?", shiftKey: true }), "?")).toBe(true)
    expect(matchShortcut(key({ key: ",", ctrlKey: true }), "ctrl+,")).toBe(true)
    expect(matchShortcut(key({ key: "ArrowLeft", altKey: true }), "alt+arrowleft")).toBe(true)
    expect(matchShortcut(key({ key: "J", shiftKey: true }), "j")).toBe(false)
  })

  it("键帽文字", () => {
    expect(shortcutKeys("ctrl+shift+l")).toEqual(["Ctrl", "Shift", "L"])
    expect(shortcutKeys("escape")).toEqual(["Esc"])
    expect(shortcutKeys("arrowup")).toEqual(["↑"])
  })
})
