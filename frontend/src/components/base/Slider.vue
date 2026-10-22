<script setup lang="ts">
// 滑块（06 第 5.2 节）：轨道 4 px，刻度下标数字，默认值的刻度下额外标“默认”；拇指 18 px 圆环；
// 拖动时上方气泡显示数值；←→ 加减一步，PageUp/PageDown 加减五步，Home/End 到两端。
import { computed, ref, useTemplateRef } from "vue"

const model = defineModel<number>({ required: true })

const props = withDefaults(
  defineProps<{
    min?: number
    max?: number
    step?: number
    ticks?: number[]
    defaultValue?: number
    ariaLabel?: string
    format?: (value: number) => string
    disabled?: boolean
  }>(),
  { min: 0, max: 100, step: 1 },
)

const track = useTemplateRef<HTMLDivElement>("track")
const dragging = ref(false)

const decimals = computed(() => {
  const s = String(props.step)
  return s.includes(".") ? (s.split(".")[1]?.length ?? 0) : 0
})

function display(value: number): string {
  return props.format ? props.format(value) : value.toFixed(decimals.value)
}

function clamp(value: number): number {
  const stepped = Math.round((value - props.min) / props.step) * props.step + props.min
  const fixed = Number(stepped.toFixed(decimals.value))
  return Math.min(props.max, Math.max(props.min, fixed))
}

const ratio = computed(() => {
  const span = props.max - props.min
  return span > 0 ? (model.value - props.min) / span : 0
})

function tickRatio(value: number): number {
  const span = props.max - props.min
  return span > 0 ? (value - props.min) / span : 0
}

function setFromPointer(clientX: number) {
  const el = track.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const r = rect.width > 0 ? (clientX - rect.left) / rect.width : 0
  model.value = clamp(props.min + Math.min(1, Math.max(0, r)) * (props.max - props.min))
}

function onPointerDown(event: PointerEvent) {
  if (props.disabled || event.button !== 0) return
  dragging.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  setFromPointer(event.clientX)
}

function onPointerMove(event: PointerEvent) {
  if (dragging.value) setFromPointer(event.clientX)
}

function onPointerUp(event: PointerEvent) {
  dragging.value = false
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
}

function onKeydown(event: KeyboardEvent) {
  if (props.disabled) return
  let next: number | null = null
  if (event.key === "ArrowRight" || event.key === "ArrowUp") next = model.value + props.step
  else if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = model.value - props.step
  else if (event.key === "PageUp") next = model.value + props.step * 5
  else if (event.key === "PageDown") next = model.value - props.step * 5
  else if (event.key === "Home") next = props.min
  else if (event.key === "End") next = props.max
  if (next === null) return
  event.preventDefault()
  model.value = clamp(next)
}
</script>

<template>
  <div class="ws-slider" :class="{ 'is-disabled': disabled, 'is-dragging': dragging }">
    <div
      ref="track"
      class="ws-slider__track-area"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <div class="ws-slider__track">
        <div class="ws-slider__range" :style="{ width: `${ratio * 100}%` }" />
      </div>
      <div
        class="ws-slider__thumb"
        role="slider"
        :tabindex="disabled ? -1 : 0"
        :aria-label="ariaLabel"
        :aria-valuemin="min"
        :aria-valuemax="max"
        :aria-valuenow="model"
        :aria-valuetext="display(model)"
        :aria-disabled="disabled || undefined"
        :style="{ left: `${ratio * 100}%` }"
        @keydown="onKeydown"
      >
        <span v-if="dragging" class="ws-slider__bubble num">{{ display(model) }}</span>
      </div>
    </div>
    <div v-if="ticks && ticks.length" class="ws-slider__ticks" aria-hidden="true">
      <span
        v-for="t in ticks"
        :key="t"
        class="ws-slider__tick"
        :class="{ 'is-default': t === defaultValue }"
        :style="{ left: `${tickRatio(t) * 100}%` }"
      >
        <span class="ws-slider__tick-mark" />
        <span class="ws-slider__tick-label num">{{ display(t) }}</span>
        <span v-if="t === defaultValue" class="ws-slider__tick-default">默认</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.ws-slider {
  position: relative;
  width: 100%;
  min-width: 200px;
  padding: 0 9px;
  user-select: none;
}

.ws-slider__track-area {
  position: relative;
  height: 24px;
  cursor: pointer;
  touch-action: none;
}

.ws-slider.is-disabled .ws-slider__track-area {
  cursor: not-allowed;
  opacity: 0.5;
}

.ws-slider__track {
  position: absolute;
  left: 0;
  right: 0;
  top: 10px;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--surface-3);
  overflow: hidden;
}

.ws-slider__range {
  height: 100%;
  background: var(--ink);
}

.ws-slider__thumb {
  position: absolute;
  top: 3px;
  width: 18px;
  height: 18px;
  margin-left: -9px;
  border: 3px solid var(--ink);
  border-radius: var(--radius-pill);
  background: var(--surface);
  transition: transform var(--dur-fast) var(--ease-out);
}

.ws-slider.is-dragging .ws-slider__thumb {
  transform: scale(1.1);
}

.ws-slider__bubble {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 2px 8px;
  border-radius: var(--radius-tooltip);
  background: var(--ink);
  color: var(--on-ink);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.ws-slider__ticks {
  position: relative;
  height: 32px;
}

.ws-slider__tick {
  position: absolute;
  top: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translateX(-50%);
}

.ws-slider__tick-mark {
  width: 1px;
  height: 4px;
  background: var(--border-strong);
}

.ws-slider__tick-label {
  color: var(--ink-2);
  font-size: var(--text-xs);
  line-height: 1.4;
}

.ws-slider__tick-default {
  color: var(--ink-2);
  font-size: 11px;
  line-height: 1.2;
}
</style>
