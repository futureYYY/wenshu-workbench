import type { Component } from "vue"

export interface SelectOption {
  value: string
  label: string
  /** 选项右侧的次要文字，如“820 毫秒” */
  hint?: string
  /** 选项下方的说明 */
  description?: string
  disabled?: boolean
}

export interface SegmentOption {
  value: string
  label: string
  /** 标签后面的计数（导视数字） */
  count?: number | string
  disabled?: boolean
}

export interface TabItem {
  value: string
  label: string
  hidden?: boolean
}

export interface MenuItem {
  key?: string
  label: string
  icon?: Component
  shortcut?: string
  danger?: boolean
  disabled?: boolean
  separator?: boolean
  heading?: boolean
  onSelect?: () => void
}
