<script setup lang="ts">
// 站点（06 第 5.1 节）：未到为空心灰环，当前为墨色粗环（带呼吸光环），已过为实心，出错、暂停另有样式。
// progress（0–1）时在圆环上画出一圈墨色弧线，用于上传进度。
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    size?: 8 | 12 | 16 | 64
    state?: "todo" | "current" | "done" | "error" | "paused"
    /** 已过站点的实心颜色（线路色等）；默认墨色 */
    color?: string
    progress?: number | null
    scale?: number
  }>(),
  { size: 12, state: "todo", progress: null, scale: 1 },
)

const STROKES: Record<number, number> = { 8: 2, 12: 2.5, 16: 3, 64: 6 }

const stroke = computed(() => {
  const base = STROKES[props.size] ?? 2
  return props.state === "current" ? base + (props.size >= 64 ? 1 : 0.5) : base
})

const r = computed(() => (props.size - stroke.value) / 2)
const c = computed(() => props.size / 2)
const circumference = computed(() => 2 * Math.PI * r.value)
const showGlyph = computed(() => props.size >= 16)
const arcOffset = computed(() =>
  props.progress === null ? 0 : circumference.value * (1 - Math.min(1, Math.max(0, props.progress))),
)
</script>

<template>
  <span
    class="ws-station"
    :class="[`is-${state}`, `size-${size}`]"
    :style="{ width: `${size}px`, height: `${size}px`, transform: scale !== 1 ? `scale(${scale})` : undefined }"
    aria-hidden="true"
  >
    <span v-if="state === 'current'" class="ws-station__halo ws-breathe" />
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
      <circle
        :cx="c"
        :cy="c"
        :r="r"
        :stroke-width="stroke"
        class="ws-station__ring"
        :style="state === 'done' && color ? { fill: color, stroke: color } : undefined"
      />
      <circle
        v-if="progress !== null"
        :cx="c"
        :cy="c"
        :r="r"
        :stroke-width="stroke"
        class="ws-station__arc"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="arcOffset"
        :transform="`rotate(-90 ${c} ${c})`"
      />
      <template v-if="showGlyph">
        <g v-if="state === 'error'" class="ws-station__glyph is-error">
          <line :x1="c" :y1="size * 0.3" :x2="c" :y2="size * 0.56" :stroke-width="Math.max(1.5, size / 12)" />
          <circle :cx="c" :cy="size * 0.7" :r="Math.max(1, size / 18)" />
        </g>
        <g v-else-if="state === 'paused'" class="ws-station__glyph is-paused">
          <line :x1="size * 0.41" :y1="size * 0.33" :x2="size * 0.41" :y2="size * 0.67" :stroke-width="Math.max(1.5, size / 12)" />
          <line :x1="size * 0.59" :y1="size * 0.33" :x2="size * 0.59" :y2="size * 0.67" :stroke-width="Math.max(1.5, size / 12)" />
        </g>
      </template>
    </svg>
  </span>
</template>

<style scoped>
.ws-station {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  transition: transform var(--dur-slow) var(--ease-out);
}

.ws-station svg {
  position: relative;
  overflow: visible;
}

.ws-station__ring {
  fill: var(--surface);
  stroke: var(--border-strong);
  transition:
    fill var(--dur-base) var(--ease-out),
    stroke var(--dur-base) var(--ease-out);
}

.is-current .ws-station__ring {
  stroke: var(--ink);
}

.is-done .ws-station__ring {
  fill: var(--ink);
  stroke: var(--ink);
}

.is-error .ws-station__ring {
  stroke: var(--status-danger);
}

.is-paused .ws-station__ring {
  stroke: var(--status-warn);
}

.ws-station__arc {
  fill: none;
  stroke: var(--ink);
  stroke-linecap: round;
  transition: stroke-dashoffset var(--dur-base) var(--ease-out);
}

.ws-station__halo {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-pill);
  background: var(--ink);
  opacity: 0.25;
  animation: ws-breathe 2s ease-in-out infinite;
}

.ws-station__glyph line {
  stroke-linecap: round;
}

.ws-station__glyph.is-error line {
  stroke: var(--status-danger);
}

.ws-station__glyph.is-error circle {
  fill: var(--status-danger);
}

.ws-station__glyph.is-paused line {
  stroke: var(--status-warn);
}
</style>
