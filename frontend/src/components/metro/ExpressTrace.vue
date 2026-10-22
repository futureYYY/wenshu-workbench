<script setup lang="ts">
// 对照阅读（06 第 5.1 节 ExpressTrace）：左栏 58% 原文段落，一条竖线贯穿，每段一个站点和编号；
// 右栏 42% 摘要主旨和要点，要点后面是来源标签。悬停或聚焦要点时来源段落高亮；
// 点击来源标签平滑滚动到该段并闪一下。↑↓ 在要点间移动，Enter 跳到第一个来源。P0 不画连线。
// 人工复核：edited 时标题旁标“人工修改”；插槽 summary 替换摘要主旨（修改时放编辑框），after-summary 放在主旨下方
// （例如可展开的“模型原摘要”）。
import { computed, nextTick, ref, useTemplateRef } from "vue"
import type { KeyPoint } from "@/api/types"
import StationDot from "./StationDot.vue"
import { animateEl } from "@/design/motion"
import { renderMarkdown } from "@/utils/markdown"

const props = defineProps<{
  segments: string[]
  summary: string
  keyPoints: KeyPoint[]
  /** 摘要主旨经过人工修改 */
  edited?: boolean
}>()

const leftPane = useTemplateRef<HTMLDivElement>("leftPane")
const pointsList = useTemplateRef<HTMLOListElement>("pointsList")
const activePoint = ref<number | null>(null)

const linked = computed(() => props.keyPoints.some((p) => p.sources.length > 0))
const activeSources = computed(() => {
  if (activePoint.value === null) return new Set<number>()
  return new Set(props.keyPoints[activePoint.value]?.sources ?? [])
})
const summaryHtml = computed(() => renderMarkdown(props.summary))

function segmentEl(n: number): HTMLElement | null {
  return leftPane.value?.querySelector<HTMLElement>(`[data-segment="${n}"]`) ?? null
}

async function jumpTo(n: number) {
  await nextTick()
  const el = segmentEl(n)
  if (!el) return
  el.scrollIntoView({ behavior: "smooth", block: "center" })
  animateEl(el, [{ backgroundColor: "var(--surface-3)" }, { backgroundColor: "transparent" }], { duration: 600, easing: "ease-out" }, true)
}

function pointButtons(): HTMLElement[] {
  return Array.from(pointsList.value?.querySelectorAll<HTMLElement>("[data-point]") ?? [])
}

function onPointKeydown(event: KeyboardEvent, index: number) {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault()
    event.stopPropagation()
    const next = Math.min(props.keyPoints.length - 1, Math.max(0, index + (event.key === "ArrowDown" ? 1 : -1)))
    pointButtons()[next]?.focus()
  } else if (event.key === "Enter") {
    const first = props.keyPoints[index]?.sources[0]
    if (first !== undefined) {
      event.preventDefault()
      void jumpTo(first)
    }
  }
}

function focusFirstPoint() {
  pointButtons()[0]?.focus()
}

defineExpose({ focusFirstPoint, jumpTo })
</script>

<template>
  <div class="ws-trace">
    <div ref="leftPane" class="ws-trace__left" aria-label="原文">
      <h2 class="ws-trace__pane-title">原文</h2>
      <ol class="ws-trace__segments">
        <li
          v-for="(seg, i) in segments"
          :key="i"
          class="ws-trace__segment"
          :class="{ 'is-active': activeSources.has(i + 1) }"
          :data-segment="i + 1"
        >
          <span class="ws-trace__stop">
            <StationDot :size="12" :state="activeSources.has(i + 1) ? 'done' : 'todo'" />
          </span>
          <span class="ws-trace__no num">{{ i + 1 }}</span>
          <p class="ws-trace__text">{{ seg }}</p>
        </li>
      </ol>
    </div>

    <div class="ws-trace__right">
      <h2 class="ws-trace__pane-title">
        摘要<span v-if="edited" class="ws-trace__tag">人工修改</span>
      </h2>
      <slot name="summary">
        <div class="ws-trace__summary" v-html="summaryHtml" />
      </slot>
      <slot name="after-summary" />
      <ol v-if="keyPoints.length" ref="pointsList" class="ws-trace__points">
        <li
          v-for="(point, i) in keyPoints"
          :key="i"
          class="ws-trace__point"
          :class="{ 'is-active': activePoint === i }"
          @mouseenter="activePoint = linked ? i : null"
          @mouseleave="activePoint = null"
        >
          <div
            class="ws-trace__point-main"
            tabindex="0"
            data-point
            :aria-label="`要点 ${i + 1}：${point.text}`"
            @focus="activePoint = linked ? i : null"
            @blur="activePoint = null"
            @keydown="onPointKeydown($event, i)"
          >
            <span class="ws-trace__point-no num">{{ i + 1 }}</span>
            <span class="ws-trace__point-text">{{ point.text }}</span>
          </div>
          <span v-if="point.sources.length" class="ws-trace__sources">
            <button
              v-for="s in point.sources"
              :key="s"
              type="button"
              class="ws-trace__source num"
              :aria-label="`跳到第 ${s} 段`"
              @click="jumpTo(s)"
            >
              [{{ s }}]
            </button>
          </span>
        </li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
.ws-trace {
  display: grid;
  grid-template-columns: 58fr 42fr;
  min-height: 0;
  height: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
  overflow: hidden;
}

.ws-trace__left,
.ws-trace__right {
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-6);
}

.ws-trace__left {
  border-right: 1px solid var(--border);
}

.ws-trace__pane-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-4);
  color: var(--ink-2);
  font-size: var(--text-sm);
  font-weight: 500;
}

.ws-trace__tag {
  padding: 0 8px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--ink-2);
  font-size: var(--text-xs);
  font-weight: 400;
  line-height: 20px;
}

.ws-trace__segments {
  position: relative;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* 贯穿段落左侧的竖线 */
.ws-trace__segments::before {
  content: "";
  position: absolute;
  top: 12px;
  bottom: 12px;
  left: 4.5px;
  width: 3px;
  border-radius: var(--radius-pill);
  background: var(--border-strong);
}

.ws-trace__segment {
  position: relative;
  display: grid;
  grid-template-columns: 12px 28px minmax(0, 680px);
  gap: var(--space-2);
  margin: 0 calc(-1 * var(--space-2));
  padding: var(--space-2);
  border-radius: var(--radius-control);
  transition: background-color var(--dur-fast) var(--ease-out);
}

.ws-trace__segment.is-active {
  background: var(--surface-2);
}

.ws-trace__stop {
  display: flex;
  padding-top: 8px;
}

.ws-trace__no {
  padding-top: 5px;
  color: var(--ink-2);
  font-size: var(--text-xs);
  text-align: right;
}

.ws-trace__text {
  margin: 0;
  font-size: var(--text-md);
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ws-trace__summary {
  font-size: var(--text-lg);
  font-weight: 500;
  line-height: 1.6;
}

.ws-trace__summary :deep(p) {
  margin: 0 0 var(--space-2);
}

.ws-trace__points {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: var(--space-5) 0 0;
  padding: 0;
  list-style: none;
}

.ws-trace__point {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2);
  border-radius: var(--radius-control);
  transition: background-color var(--dur-fast) var(--ease-out);
}

.ws-trace__point.is-active {
  background: var(--surface-2);
}

.ws-trace__point-main {
  display: flex;
  gap: var(--space-3);
  min-width: 0;
  border-radius: 4px;
}

.ws-trace__point-no {
  flex-shrink: 0;
  min-width: 18px;
  color: var(--ink-2);
  font-weight: 700;
}

.ws-trace__point-text {
  font-size: var(--text-md);
  line-height: 1.7;
}

.ws-trace__sources {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
  flex-shrink: 0;
  max-width: 120px;
}

.ws-trace__source {
  height: 22px;
  padding: 0 6px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-trace__source:hover {
  border-color: var(--ink);
  color: var(--ink);
}
</style>
