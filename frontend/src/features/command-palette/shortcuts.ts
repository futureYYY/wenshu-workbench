/** 快捷键一览（06 第 7.3 节），快捷键一览对话框和命令面板共用。 */

export interface ShortcutRow {
  keys: string[]
  action: string
  scope: string
}

export const SHORTCUTS: ShortcutRow[] = [
  { keys: ["ctrl+k"], action: "命令面板", scope: "全局" },
  { keys: ["ctrl+n"], action: "新建任务", scope: "全局" },
  { keys: ["ctrl+,"], action: "设置", scope: "全局" },
  { keys: ["ctrl+shift+l"], action: "切换亮色、暗色", scope: "全局" },
  { keys: ["?"], action: "快捷键一览", scope: "全局，焦点不在输入框时" },
  { keys: ["escape"], action: "关闭最上层浮层；没有浮层时清除筛选", scope: "全局" },
  { keys: ["enter"], action: "下一站；最后一站为开始处理", scope: "新建任务" },
  { keys: ["alt+arrowleft"], action: "上一站", scope: "新建任务" },
  { keys: ["ctrl+v"], action: "用剪贴板文本开始", scope: "首页、新建任务第一站" },
  { keys: ["arrowup", "arrowdown"], action: "上一条、下一条", scope: "结果表、条目抽屉、对照阅读" },
  { keys: ["k", "j"], action: "上一条、下一条", scope: "结果表、条目抽屉、对照阅读" },
  { keys: ["enter"], action: "打开条目详情", scope: "结果表" },
  { keys: ["/"], action: "聚焦搜索框", scope: "结果表、任务中心" },
  { keys: ["p"], action: "暂停或继续当前任务", scope: "任务详情" },
  { keys: ["r"], action: "重新处理当前条目", scope: "条目抽屉" },
  { keys: ["e"], action: "修正意图或修改摘要", scope: "结果表、条目抽屉、对照阅读" },
  { keys: ["space"], action: "标记已复核（再按一次取消）", scope: "结果表" },
  { keys: ["ctrl+s"], action: "保存", scope: "提示词工坊" },
  { keys: ["ctrl+enter"], action: "试运行", scope: "提示词工坊" },
]
