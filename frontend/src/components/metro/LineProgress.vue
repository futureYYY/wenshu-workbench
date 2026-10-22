<script setup lang="ts">
// 线路进度（06 第 5.1 节）。迷你：列表行里，线宽 3 px，右侧“62/100”；完整：任务详情顶部，线宽 6 px，
// 左边大号百分比，下方数据行。线段依次为跳过、成功、失败，之后是未完成的轨道；
// 已完成部分的末端是“当前”站点，暂停时换成暂停站点，完成时终点站变实心。
import { computed, onBeforeUnmount, ref, watch } from "vue"
import type { JobProgress, JobStatus } from "@/api/types"
import AnimatedNumber from "@/components/base/AnimatedNumber.vue"
import { formatDuration, formatEta, formatNumber, secondsBetween } from "@/utils/format"
import StationDot from "./StationDot.vue"

const props = withDefaults(
  defineProps<{
    progress: JobProgress
    status: JobStatus
    variant?: "mini" | "full"
    width?: number
    startedAt?: string | null
    finishedAt?: string | null
  }>(),
  { variant: "mini", width: 200, startedAt: null, finishedAt: null },
)

const total = computed(() => Math.max(0, props.progress.total))
const done = computed(() => props.progress.succeeded + props.progress.failed + props.progress.skipped)

function pct(n: number): number {
  return total.value > 0 ? Math.min(100, (n / total.value) * 100) : 0
}

const skipPct = computed(() => pct(props.progress.skipped))
const okPct = computed(() => pct(props.progress.succeeded))
const failPct = computed(() => pct(props.progress.failed))
const donePct = computed(() => Math.min(100, skipPct.value + okPct.value + failPct.value))

const finished = computed(() => props.status === "completed")
const markerState = computed<"current" | "paused" | "done" | "todo">(() => {
  if (props.status === "paused") return "paused"
  if (props.status === "completed") return "done"
  if (props.status === "cancelled") return "todo"
  return "current"
})

const bigPercent = computed(() => {
  if (finished.value) return 100
  return Math.floor(props.progress.percent)
})

const elapsed = computed(() => secondsBetween(props.startedAt, props.finishedAt))

const ariaText = computed(() => `已完成 ${formatNumber(done.value)} 条，共 ${formatNumber(total.value)} 条`)

// 进度播报：aria-live，最多每 10 秒一次（06 第 10 节）
const announced = ref(ariaText.value)
let lastAnnounce = 0
let pendingTimer: number | undefined
watch(ariaText, (text) => {
  if (props.variant !== "full") return
  const now = Date.now()
  const wait = 10_000 - (now - lastAnnounce)
  window.clearTimeout(pendingTimer)
  if (wait <= 0) {
    lastAnnounce = now
    announced.value = text
  } else {
    pendingTimer = window.setTimeout(() => {
      lastAnnounce = Date.now()
      announced.value = ariaText.value
    }, wait)
  }
})
onBeforeUnmount(() => window.clearTimeout(pendingTimer))
</script>

<template>
  <div
    v-if="variant === 'mini'"
    class="ws-lp ws-lp--mini"
    :style="{ width: `${width}px` }"
    role="progressbar"
    :aria-valuemin="0"
    :aria-valuemax="total"
    :aria-valuenow="done"
    :aria-valuetext="ariaText"
  >
    <div class="ws-lp__rail">
      <span class="ws-lp__seg is-skip" :style="{ width: `${skipPct}%` }" />
      <span class="ws-lp__seg is-ok" :style="{ width: `${okPct}%` }" />
      <span class="ws-lp__seg is-fail" :style="{ width: `${failPct}%` }" />
      <span class="ws-lp__marker" :style="{ left: `${donePct}%` }">
        <StationDot :size="8" :state="markerState" />
      </span>
    </div>
    <span class="ws-lp__count num">{{ formatNumber(done) }}/{{ formatNumber(total) }}</span>
  </div>

  <div v-else class="ws-lp ws-lp--full">
    <div class="ws-lp__big num" aria-hidden="true">
      <AnimatedNumber :value="bigPercent" /><span class="ws-lp__big-unit">%</span>
    </div>
    <div class="ws-lp__main">
      <div
        class="ws-lp__line"
        role="progressbar"
        :aria-valuemin="0"
        :aria-valuemax="total"
        :aria-valuenow="done"
        :aria-valuetext="ariaText"
      >
        <StationDot :size="12" state="done" class="ws-lp__start" />
        <div class="ws-lp__rail is-full">
          <span class="ws-lp__seg is-skip" :style="{ width: `${skipPct}%` }" />
          <span class="ws-lp__seg is-ok" :style="{ width: `${okPct}%` }" />
          <span class="ws-lp__seg is-fail" :style="{ width: `${failPct}%` }" />
          <span v-if="!finished" class="ws-lp__marker" :style="{ left: `${donePct}%` }">
            <StationDot :size="16" :state="markerState" />
          </span>
        </div>
        <StationDot :size="16" :state="finished ? 'done' : 'todo'" class="ws-lp__end" />
      </div>
      <div class="ws-lp__data">
        <span>
          已完成 <AnimatedNumber class="ws-lp__num" :value="done" /> / <span class="num">{{ formatNumber(total) }}</span>
        </span>
        <span v-if="progress.failed > 0" class="ws-lp__failed">
          失败 <AnimatedNumber class="ws-lp__num" :value="progress.failed" />
        </span>
        <template v-if="!finished && status !== 'cancelled'">
          <span v-if="progress.rate_per_min !== null">
            <span class="num ws-lp__num">{{ Math.round(progress.rate_per_min) }}</span> 条/分
          </span>
          <span v-if="progress.eta_seconds !== null && status === 'running'">{{ formatEta(progress.eta_seconds) }}后完成</span>
        </template>
        <span v-else-if="elapsed !== null">用时 {{ formatDuration(elapsed) }}</span>
      </div>
    </div>
    <span class="sr-only" aria-live="polite">{{ announced }}</span>
  </div>
</template>

<style scoped>
.ws-lp--mini {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 160px;
  max-width: 240px;
}

.ws-lp__rail {
  position: relative;
  display: flex;
  flex: 1;
  height: 3px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
}

.ws-lp__rail.is-full {
  height: 6px;
}

.ws-lp__seg {
  height: 100%;
  transition: width var(--dur-number) var(--ease-move);
}

.ws-lp__seg:first-child {
  border-radius: var(--radius-pill) 0 0 var(--radius-pill);
}

.ws-lp__seg.is-skip {
  background: var(--ink-3);
}

.ws-lp__seg.is-ok {
  background: var(--ink);
}

.ws-lp__seg.is-fail {
  background: var(--status-danger);
}

.ws-lp__marker {
  position: absolute;
  top: 50%;
  display: inline-flex;
  transform: translate(-50%, -50%);
  transition: left var(--dur-number) var(--ease-move);
}

.ws-lp__count {
  flex-shrink: 0;
  min-width: 56px;
  color: var(--ink-2);
  font-size: var(--text-sm);
  text-align: right;
}

.ws-lp--full {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  width: 100%;
  /* 新建任务的步骤条通过 View Transitions 变成任务详情顶部的线路进度 */
  view-transition-name: metro-line;
}

.ws-lp__big {
  display: flex;
  align-items: baseline;
  min-width: 132px;
  font-size: var(--text-num-xl);
  font-weight: 800;
  line-height: 1;
}

.ws-lp__big-unit {
  margin-left: 2px;
  color: var(--ink-2);
  font-size: var(--text-xl);
  font-weight: 700;
}

.ws-lp__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}

.ws-lp__line {
  display: flex;
  align-items: center;
  gap: 0;
}

.ws-lp__start {
  margin-right: -2px;
}

.ws-lp__end {
  margin-left: -2px;
}

.ws-lp__data {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-lp__num {
  color: var(--ink);
  font-size: var(--text-md);
  font-weight: 700;
}

.ws-lp__failed .ws-lp__num {
  color: var(--status-danger);
}
</style>
