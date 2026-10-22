<script setup lang="ts">
// 分段控件（06 第 5.2 节）：整体胶囊、--surface-2 底；选中项是白色胶囊，切换时指示器滑动（220 ms）。
// 语义上是单选组：←→ 切换。
import { useResizeObserver } from "@vueuse/core"
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from "vue"
import type { SegmentOption } from "./types"

const model = defineModel<string>({ required: true })

const props = withDefaults(
  defineProps<{
    options: SegmentOption[]
    ariaLabel?: string
    size?: "sm" | "md"
  }>(),
  { size: "md" },
)

const root = useTemplateRef<HTMLDivElement>("root")
const indicator = ref<{ left: number; width: number } | null>(null)

const activeIndex = computed(() => props.options.findIndex((o) => o.value === model.value))

function measure() {
  const el = root.value
  if (!el) return
  const button = el.querySelectorAll<HTMLButtonElement>("button[role='radio']")[activeIndex.value]
  indicator.value = button ? { left: button.offsetLeft, width: button.offsetWidth } : null
}

onMounted(() => void nextTick(measure))
watch([activeIndex, () => props.options.map((o) => `${o.label}${o.count ?? ""}`).join("|")], () => void nextTick(measure))
useResizeObserver(root, () => measure())

function select(index: number) {
  const opt = props.options[index]
  if (!opt || opt.disabled) return
  model.value = opt.value
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return
  event.preventDefault()
  const dir = event.key === "ArrowRight" ? 1 : -1
  const n = props.options.length
  let i = activeIndex.value
  for (let step = 0; step < n; step++) {
    i = (i + dir + n) % n
    if (!props.options[i]?.disabled) break
  }
  select(i)
  void nextTick(() => {
    root.value?.querySelectorAll<HTMLButtonElement>("button[role='radio']")[i]?.focus()
  })
}
</script>

<template>
  <div
    ref="root"
    class="ws-seg"
    :class="`ws-seg--${size}`"
    role="radiogroup"
    :aria-label="ariaLabel"
    @keydown="onKeydown"
  >
    <span
      v-if="indicator"
      class="ws-seg__indicator"
      aria-hidden="true"
      :style="{ transform: `translateX(${indicator.left}px)`, width: `${indicator.width}px` }"
    />
    <button
      v-for="(opt, i) in options"
      :key="opt.value"
      type="button"
      role="radio"
      class="ws-seg__item"
      :class="{ 'is-active': i === activeIndex }"
      :aria-checked="i === activeIndex"
      :tabindex="i === activeIndex || (activeIndex < 0 && i === 0) ? 0 : -1"
      :disabled="opt.disabled"
      @click="select(i)"
    >
      <span>{{ opt.label }}</span>
      <span v-if="opt.count !== undefined" class="ws-seg__count num">{{ opt.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.ws-seg {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  isolation: isolate;
}

.ws-seg__indicator {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 0;
  z-index: -1;
  border-radius: var(--radius-pill);
  background: var(--surface);
  box-shadow: 0 0 0 1px var(--border);
  transition:
    transform var(--dur-base) var(--ease-move),
    width var(--dur-base) var(--ease-move);
}

.ws-seg__item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 var(--space-3);
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--ink-2);
  font-size: var(--text-base);
  font-weight: 500;
  white-space: nowrap;
  transition: color var(--dur-fast) var(--ease-out);
}

.ws-seg--sm .ws-seg__item {
  height: 24px;
  padding: 0 10px;
  font-size: var(--text-sm);
}

.ws-seg__item.is-active {
  color: var(--ink);
}

.ws-seg__item:disabled {
  color: var(--ink-3);
}

.ws-seg__count {
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-seg__item.is-active .ws-seg__count {
  color: var(--ink-2);
}
</style>
