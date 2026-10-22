<script setup lang="ts">
// 状态标签：图标 + 文字，状态色；颜色从不单独表达状态（06 第 5.2、10 节）。运行中的图标是一个呼吸的小圆点。
import { Ban, CircleCheck, CircleMinus, CircleX, Clock, Pause } from "@lucide/vue"
import { computed, type Component } from "vue"
import type { ItemStatus, JobStatus } from "@/api/types"

const props = withDefaults(
  defineProps<{
    status: JobStatus | ItemStatus
    kind?: "job" | "item"
    size?: "sm" | "md"
    label?: string
  }>(),
  { kind: "job", size: "md" },
)

interface Look {
  text: string
  tone: "running" | "ok" | "warn" | "danger" | "muted"
  icon: Component | null
}

const JOB: Record<JobStatus, Look> = {
  queued: { text: "排队中", tone: "muted", icon: Clock },
  running: { text: "运行中", tone: "running", icon: null },
  paused: { text: "已暂停", tone: "warn", icon: Pause },
  completed: { text: "已完成", tone: "ok", icon: CircleCheck },
  cancelled: { text: "已取消", tone: "muted", icon: Ban },
}

const ITEM: Record<ItemStatus, Look> = {
  pending: { text: "等待中", tone: "muted", icon: Clock },
  running: { text: "处理中", tone: "running", icon: null },
  succeeded: { text: "成功", tone: "ok", icon: CircleCheck },
  failed: { text: "失败", tone: "danger", icon: CircleX },
  skipped: { text: "跳过", tone: "muted", icon: CircleMinus },
}

const look = computed<Look>(() => {
  if (props.kind === "item") return ITEM[props.status as ItemStatus] ?? ITEM.pending
  return JOB[props.status as JobStatus] ?? JOB.queued
})
</script>

<template>
  <span class="ws-chip" :class="[`tone-${look.tone}`, `ws-chip--${size}`]">
    <span v-if="!look.icon" class="ws-chip__dot" aria-hidden="true"><span class="ws-breathe" /></span>
    <component :is="look.icon" v-else :size="size === 'sm' ? 13 : 14" :stroke-width="2" aria-hidden="true" />
    <span>{{ label ?? look.text }}</span>
  </span>
</template>

<style scoped>
.ws-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--text-sm);
  font-weight: 500;
  white-space: nowrap;
}

.ws-chip--sm {
  font-size: var(--text-xs);
}

.tone-running {
  color: var(--status-running);
}

.tone-ok {
  color: var(--status-ok);
}

.tone-warn {
  color: var(--status-warn);
}

.tone-danger {
  color: var(--status-danger);
}

.tone-muted {
  color: var(--status-muted);
}

.ws-chip__dot {
  position: relative;
  display: inline-block;
  width: 8px;
  height: 8px;
  margin: 0 3px;
  border-radius: var(--radius-pill);
  background: currentColor;
}

.ws-chip__dot > span {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-pill);
  background: currentColor;
  animation: ws-breathe 2s ease-in-out infinite;
}
</style>
