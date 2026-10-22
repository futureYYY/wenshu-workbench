<script setup lang="ts">
// 标签页（06 第 5.2 节）：文字标签，选中项下方 2 px 墨线，切换时墨线滑动（220 ms）。
// 只渲染标签栏；内容由父组件按 v-model 的值切换，面板请加 role="tabpanel" 和 :aria-labelledby="tabId(value)"。
import { useResizeObserver } from "@vueuse/core"
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from "vue"
import type { TabItem } from "./types"

const model = defineModel<string>({ required: true })

const props = defineProps<{
  items: TabItem[]
  ariaLabel?: string
  idPrefix?: string
}>()

const root = useTemplateRef<HTMLDivElement>("root")
const bar = ref<{ left: number; width: number } | null>(null)
const visible = computed(() => props.items.filter((t) => !t.hidden))
const activeIndex = computed(() => visible.value.findIndex((t) => t.value === model.value))

function tabId(value: string): string {
  return `${props.idPrefix ?? "tab"}-${value}`
}

function measure() {
  const el = root.value
  if (!el) return
  const tab = el.querySelectorAll<HTMLButtonElement>("button[role='tab']")[activeIndex.value]
  bar.value = tab ? { left: tab.offsetLeft, width: tab.offsetWidth } : null
}

onMounted(() => void nextTick(measure))
watch([activeIndex, () => visible.value.map((t) => t.label).join("|")], () => void nextTick(measure))
useResizeObserver(root, () => measure())

function onKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") return
  event.preventDefault()
  const n = visible.value.length
  if (n === 0) return
  let i = activeIndex.value
  if (event.key === "ArrowRight") i = (i + 1) % n
  else if (event.key === "ArrowLeft") i = (i - 1 + n) % n
  else if (event.key === "Home") i = 0
  else i = n - 1
  const next = visible.value[i]
  if (!next) return
  model.value = next.value
  void nextTick(() => root.value?.querySelectorAll<HTMLButtonElement>("button[role='tab']")[i]?.focus())
}

defineExpose({ tabId })
</script>

<template>
  <div ref="root" class="ws-tabs" role="tablist" :aria-label="ariaLabel" @keydown="onKeydown">
    <button
      v-for="tab in visible"
      :id="tabId(tab.value)"
      :key="tab.value"
      type="button"
      role="tab"
      class="ws-tabs__tab"
      :class="{ 'is-active': tab.value === model }"
      :aria-selected="tab.value === model"
      :tabindex="tab.value === model ? 0 : -1"
      @click="model = tab.value"
    >
      {{ tab.label }}
    </button>
    <span
      v-if="bar"
      class="ws-tabs__bar"
      aria-hidden="true"
      :style="{ transform: `translateX(${bar.left}px)`, width: `${bar.width}px` }"
    />
  </div>
</template>

<style scoped>
.ws-tabs {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: var(--space-5);
  border-bottom: 1px solid var(--border);
}

.ws-tabs__tab {
  height: 40px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font-size: var(--text-base);
  font-weight: 500;
  white-space: nowrap;
  transition: color var(--dur-fast) var(--ease-out);
}

.ws-tabs__tab:hover,
.ws-tabs__tab.is-active {
  color: var(--ink);
}

.ws-tabs__bar {
  position: absolute;
  left: 0;
  bottom: -1px;
  height: 2px;
  background: var(--ink);
  transition:
    transform var(--dur-base) var(--ease-move),
    width var(--dur-base) var(--ease-move);
}
</style>
