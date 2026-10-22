import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import StatusChip from "./StatusChip.vue"

describe("StatusChip", () => {
  it("任务状态总是配文字", () => {
    expect(mount(StatusChip, { props: { status: "paused" } }).text()).toContain("已暂停")
    expect(mount(StatusChip, { props: { status: "completed" } }).text()).toContain("已完成")
  })

  it("条目状态用条目的说法", () => {
    expect(mount(StatusChip, { props: { status: "pending", kind: "item" } }).text()).toContain("等待中")
    expect(mount(StatusChip, { props: { status: "failed", kind: "item" } }).text()).toContain("失败")
  })

  it("运行中显示呼吸的小圆点而不是图标", () => {
    const wrapper = mount(StatusChip, { props: { status: "running" } })
    expect(wrapper.find(".ws-chip__dot").exists()).toBe(true)
    expect(wrapper.find("svg").exists()).toBe(false)
  })
})
