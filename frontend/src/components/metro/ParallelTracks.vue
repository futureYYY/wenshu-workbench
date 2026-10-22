<script setup lang="ts">
// 并行轨道（06 第 5.1 节）：运行中显示每个并发槽正在处理什么，行数等于任务并发数。
// 每行一条 2 px 轨道线，上面是一个“车厢”胶囊：第 N 行、原文预览、已用时（每 100 ms 更新）。
// 等待重试时描边改为警告色虚线并倒计时；分段时带“第 2/5 段”标签；纠正输出时显示“纠正输出格式”。
import { computed, onBeforeUnmount, ref, watch } from "vue"
import type { JobStatus, Track } from "@/api/types"
import { formatNumber, formatShortMs } from "@/utils/format"

const props = defineProps<{
  tracks: Track[]
  concurrency: number
  status: JobStatus
}>()

// 每个条目固定在一个槽里，车厢不会在行之间跳动
const slots = ref<(number | null)[]>([])

watch(
  [() => props.tracks, () => props.concurrency],
  ([list, concurrency]) => {
    const ids = new Set(list.map((t) => t.item_id))
    const size = Math.max(concurrency, list.length)
    const next: (number | null)[] = Array.from({ length: size }, (_, i) => slots.value[i] ?? null)
    for (let i = 0; i < next.length; i++) {
      const id = next[i]
      if (id !== null && id !== undefined && !ids.has(id)) next[i] = null
    }
    for (const t of list) {
      if (next.includes(t.item_id)) continue
      const free = next.indexOf(null)
      if (free >= 0) next[free] = t.item_id
      else next.push(t.item_id)
    }
    // 槽数收缩到并发数（多出来的槽只在空闲时移除）
    while (next.length > concurrency && next[next.length - 1] === null) next.pop()
    slots.value = next
  },
  { immediate: true, deep: false },
)

const byId = computed(() => new Map(props.tracks.map((t) => [t.item_id, t])))

const rowHeight = computed(() => {
  const n = slots.value.length
  if (n <= 8) return 40
  if (n <= 14) return 32
  return 26
})

// 已用时：用 requestAnimationFrame 每 100 ms 更新一次
const now = ref(Date.now())
let frame: number | null = null
let last = 0

function loop(ts: number) {
  if (ts - last >= 100) {
    last = ts
    now.value = Date.now()
  }
  frame = requestAnimationFrame(loop)
}

watch(
  () => props.tracks.length > 0,
  (active) => {
    if (active && frame === null && typeof requestAnimationFrame === "function") frame = requestAnimationFrame(loop)
    if (!active && frame !== null) {
      cancelAnimationFrame(frame)
      frame = null
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (frame !== null) cancelAnimationFrame(frame)
})

function elapsed(track: Track): string {
  const start = new Date(track.started_at).getTime()
  return formatShortMs(Math.max(0, now.value - start))
}

function retryText(track: Track): string {
  const detail = track.phase_detail || "等待重试"
  if (!track.retry_at) return detail
  const remaining = Math.max(0, Math.ceil((new Date(track.retry_at).getTime() - now.value) / 1000))
  return /\d+(?= 秒后重试)/.test(detail) ? detail.replace(/\d+(?= 秒后重试)/, String(remaining)) : `${detail}，${remaining} 秒后重试`
}

function phaseTag(track: Track): string | null {
  if (track.phase === "chunk") return track.phase_detail || "分段摘要"
  if (track.phase === "merge") return track.phase_detail || "合并各段摘要"
  return null
}

const paused = computed(() => props.status === "paused" || props.status === "cancelled")
const idle = computed(() => props.tracks.length === 0)
</script>

<template>
  <section class="ws-tracks" :aria-label="`并行处理 ${concurrency} 条`">
    <header class="ws-tracks__head">
      <span>并行处理 <span class="num">{{ formatNumber(concurrency) }}</span> 条</span>
      <span v-if="paused && !idle" class="ws-tracks__note">已暂停，正在处理的条目完成后停下</span>
    </header>

    <p v-if="paused && idle" class="ws-tracks__paused">已暂停，正在处理的条目都已完成</p>

    <ol v-else class="ws-tracks__rows" :style="{ '--row-h': `${rowHeight}px` }">
      <li v-for="(id, index) in slots" :key="index" class="ws-tracks__row" :class="{ 'is-idle': id === null }">
        <span class="ws-tracks__rail" aria-hidden="true" />
        <Transition name="ws-car" mode="out-in">
          <div
            v-if="id !== null && byId.get(id)"
            :key="id"
            class="ws-tracks__car"
            :class="`phase-${byId.get(id)!.phase}`"
          >
            <span class="ws-tracks__row-no">第 <span class="num">{{ byId.get(id)!.row_number }}</span> 行</span>
            <template v-if="byId.get(id)!.phase === 'waiting_retry'">
              <span class="ws-tracks__text is-warn">{{ retryText(byId.get(id)!) }}</span>
            </template>
            <template v-else-if="byId.get(id)!.phase === 'parse_repair'">
              <span class="ws-tracks__text">纠正输出格式</span>
              <span class="ws-tracks__time num">{{ elapsed(byId.get(id)!) }}</span>
            </template>
            <template v-else>
              <span v-if="phaseTag(byId.get(id)!)" class="ws-tracks__tag">{{ phaseTag(byId.get(id)!) }}</span>
              <span class="ws-tracks__text">{{ byId.get(id)!.input_preview }}</span>
              <span class="ws-tracks__time num">{{ elapsed(byId.get(id)!) }}</span>
            </template>
          </div>
          <span v-else key="idle" class="ws-tracks__idle">空闲</span>
        </Transition>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.ws-tracks {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}

.ws-tracks__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-tracks__head .num {
  color: var(--ink);
  font-weight: 700;
}

.ws-tracks__note {
  color: var(--status-warn);
}

.ws-tracks__paused {
  margin: 0;
  padding: var(--space-8) 0;
  color: var(--status-warn);
  text-align: center;
}

.ws-tracks__rows {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-tracks__row {
  position: relative;
  display: flex;
  align-items: center;
  height: var(--row-h);
  padding: 0 var(--space-2);
}

.ws-tracks__rail {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 2px;
  margin-top: -1px;
  background: var(--border);
}

.ws-tracks__row.is-idle .ws-tracks__rail {
  background: transparent;
  background-image: repeating-linear-gradient(to right, var(--border) 0 6px, transparent 6px 12px);
}

.ws-tracks__car {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  max-width: calc(100% - 24px);
  height: calc(var(--row-h) - 10px);
  padding: 0 var(--space-3);
  border: 1.5px solid var(--ink);
  border-radius: var(--radius-pill);
  background: var(--surface);
  font-size: var(--text-sm);
}

.ws-tracks__car.phase-waiting_retry {
  border-style: dashed;
  border-color: var(--status-warn);
}

.ws-tracks__row-no {
  flex-shrink: 0;
  color: var(--ink);
  white-space: nowrap;
}

.ws-tracks__row-no .num {
  font-weight: 700;
}

.ws-tracks__text {
  overflow: hidden;
  color: var(--ink-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-tracks__text.is-warn {
  color: var(--status-warn);
}

.ws-tracks__tag {
  flex-shrink: 0;
  padding: 0 6px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--ink-2);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.ws-tracks__time {
  flex-shrink: 0;
  margin-left: auto;
  color: var(--ink);
}

.ws-tracks__idle {
  position: relative;
  margin: 0 auto;
  padding: 0 var(--space-2);
  background: var(--surface);
  color: var(--ink-2);
  font-size: var(--text-xs);
}

/* 一条处理完：车厢向右滑出 16 px 并淡出；新车厢从左侧滑入（各 160 ms） */
.ws-car-leave-active {
  transition:
    transform var(--dur-car) var(--ease-in),
    opacity var(--dur-car) var(--ease-in);
}

.ws-car-leave-to {
  transform: translateX(16px);
  opacity: 0;
}

.ws-car-enter-active {
  transition:
    transform var(--dur-car) var(--ease-out),
    opacity var(--dur-car) var(--ease-out);
}

.ws-car-enter-from {
  transform: translateX(-16px);
  opacity: 0;
}
</style>
