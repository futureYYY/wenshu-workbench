<script setup lang="ts">
// 线网图（06 第 5.1 节）：意图识别结果的主角。
// 左侧是枢纽胶囊，线路按条数从多到少、从上到下排列，右侧 260 px 放终点站标签；
// 悬停一条线时其余降到 0.2 不透明度并显示示例原文；点击按该意图筛选（Shift 多选）；
// 新意图出现时播放“开通新线路”，全部完成时终点站依次点亮。
import { useResizeObserver } from "@vueuse/core"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, useTemplateRef, watch } from "vue"
import type { CategoryStat } from "@/api/types"
import AnimatedNumber from "@/components/base/AnimatedNumber.vue"
import Popover from "@/components/base/Popover.vue"
import { animateEl, DUR, EASE } from "@/design/motion"
import { glowFilter, lineStyle } from "@/design/palette"
import { useUiStore } from "@/stores/ui"
import { formatNumber, formatPercent } from "@/utils/format"
import { clip } from "@/utils/text"
import {
  buildLines,
  describeLineMap,
  layoutLineMap,
  OTHER_KEY,
  orderLines,
  type MapLine,
} from "./lineMapGeometry"

const props = withDefaults(
  defineProps<{
    categories: CategoryStat[]
    failed: number
    running: boolean
    selected?: string[]
    /** 固定高度；不给时按容器高度 */
    height?: number | null
    /** 悬停时取 3 条示例原文 */
    loadSamples?: (label: string) => Promise<string[]>
  }>(),
  { selected: () => [], height: null },
)

const emit = defineEmits<{
  toggle: [labels: string[], additive: boolean]
  showFailed: []
}>()

const ui = useUiStore()
const root = useTemplateRef<HTMLDivElement>("root")
const svg = useTemplateRef<SVGSVGElement>("svg")
const size = ref({ width: 720, height: 320 })

useResizeObserver(root, (entries) => {
  const rect = entries[0]?.contentRect
  if (rect) size.value = { width: Math.max(360, rect.width), height: Math.max(200, rect.height) }
})

// ---- 线路顺序：运行中最多每 2 秒重排一次 ----
const specs = computed(() => buildLines(props.categories))
const order = ref<string[] | null>(null)
let lastReorder = 0
let reorderTimer: number | undefined

function reorder() {
  order.value = specs.value.map((s) => s.key)
  lastReorder = Date.now()
}

watch(
  specs,
  () => {
    const now = Date.now()
    if (!props.running || order.value === null || now - lastReorder >= DUR.reorderGap) {
      reorder()
    } else if (reorderTimer === undefined) {
      reorderTimer = window.setTimeout(() => {
        reorderTimer = undefined
        reorder()
      }, DUR.reorderGap - (now - lastReorder))
    }
  },
  { immediate: true },
)

const ordered = computed(() => orderLines(specs.value, order.value))
const total = computed(() => props.categories.reduce((s, c) => s + c.count, 0))

const layout = computed(() =>
  layoutLineMap({
    lines: ordered.value,
    failed: props.failed,
    width: size.value.width,
    height: props.height ?? size.value.height,
  }),
)

const ariaLabel = computed(() => describeLineMap(total.value, ordered.value, props.failed, formatNumber))
const isDark = computed(() => ui.resolvedTheme === "dark")
const selectedSet = computed(() => new Set(props.selected))

function styleOf(line: MapLine) {
  return lineStyle(line.colorIndex, ui.resolvedTheme)
}

function isSelected(line: MapLine): boolean {
  return line.members.some((m) => selectedSet.value.has(m))
}

// ---- 悬停 ----
const hovered = ref<string | null>(null)
const tipFor = ref<MapLine | null>(null)
const samples = shallowRef(new Map<string, string[] | "loading">())
let hoverTimer: number | undefined

function onEnter(line: MapLine) {
  hovered.value = line.key
  window.clearTimeout(hoverTimer)
  hoverTimer = window.setTimeout(() => {
    tipFor.value = line
    if (line.key !== OTHER_KEY) void ensureSamples(line.label)
  }, 300)
}

function onLeave() {
  hovered.value = null
  tipFor.value = null
  window.clearTimeout(hoverTimer)
}

async function ensureSamples(label: string) {
  if (!props.loadSamples || samples.value.has(label)) return
  const next = new Map(samples.value)
  next.set(label, "loading")
  samples.value = next
  try {
    const list = await props.loadSamples(label)
    const done = new Map(samples.value)
    done.set(label, list)
    samples.value = done
  } catch {
    const failed = new Map(samples.value)
    failed.delete(label)
    samples.value = failed
  }
}

function lineOpacity(line: MapLine): number {
  if (hovered.value && hovered.value !== line.key) return 0.2
  return 1
}

// ---- 点击与键盘 ----
const otherOpen = ref(false)

function onLabelClick(line: MapLine, event: MouseEvent) {
  if (line.key === OTHER_KEY) {
    otherOpen.value = true
    return
  }
  emit("toggle", [line.label], event.shiftKey)
}

function onLabelsKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return
  const buttons = Array.from(root.value?.querySelectorAll<HTMLButtonElement>("[data-terminal]") ?? [])
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
  if (index < 0) return
  event.preventDefault()
  const next = buttons[Math.min(buttons.length - 1, Math.max(0, index + (event.key === "ArrowDown" ? 1 : -1)))]
  next?.focus()
}

// ---- 动效：开通新线路、全部到站 ----
const known = new Set<string>()
const freshKeys = ref(new Set<string>())
let mounted = false

function lineEl(key: string, part: "path" | "station" | "label"): Element | null {
  const scope = part === "label" ? root.value : svg.value
  return scope?.querySelector(`[data-${part}="${CSS.escape(key)}"]`) ?? null
}

async function playOpenings(keys: string[]) {
  await nextTick()
  keys.forEach((key, i) => {
    const delay = i * DUR.stagger
    const path = lineEl(key, "path") as SVGPathElement | null
    const len = path && typeof path.getTotalLength === "function" ? path.getTotalLength() : 0
    if (path && len > 0) {
      animateEl(
        path,
        [
          { strokeDasharray: `${len} ${len}`, strokeDashoffset: `${len}` },
          { strokeDasharray: `${len} ${len}`, strokeDashoffset: "0" },
        ],
        { duration: DUR.line, delay, easing: EASE.out, fill: "backwards" },
      )
    }
    animateEl(
      lineEl(key, "station"),
      [{ transform: "scale(0.6)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }],
      { duration: DUR.pop, delay: delay + DUR.line, easing: EASE.out, fill: "backwards" },
    )
    animateEl(lineEl(key, "label"), [{ opacity: 0 }, { opacity: 1 }], {
      duration: DUR.base,
      delay: delay + DUR.line,
      easing: EASE.out,
      fill: "backwards",
    })
  })
  window.setTimeout(() => {
    const next = new Set(freshKeys.value)
    for (const k of keys) next.delete(k)
    freshKeys.value = next
  }, DUR.line + keys.length * DUR.stagger + DUR.pop + 100)
}

watch(
  () => specs.value.map((s) => s.key),
  (keys) => {
    const added = keys.filter((k) => !known.has(k))
    for (const k of added) known.add(k)
    if (!mounted || !props.running || added.length === 0) return
    freshKeys.value = new Set([...freshKeys.value, ...added])
    void playOpenings(added)
  },
  { immediate: true },
)

watch(
  () => props.running,
  async (now, before) => {
    if (before && !now) {
      // 全部到站：终点站从上到下依次点亮
      reorder()
      await nextTick()
      layout.value.lines.forEach((line, i) => {
        animateEl(
          lineEl(line.key, "station"),
          [{ transform: "scale(1)" }, { transform: "scale(1.35)" }, { transform: "scale(1)" }],
          { duration: DUR.slow, delay: i * DUR.lightUp, easing: EASE.out },
        )
      })
    }
  },
)

onMounted(() => {
  mounted = true
})

onBeforeUnmount(() => {
  window.clearTimeout(reorderTimer)
  window.clearTimeout(hoverTimer)
})

const otherLine = computed(() => layout.value.lines.find((l) => l.key === OTHER_KEY) ?? null)
const otherMembers = computed(() => {
  const members = new Set(otherLine.value?.members ?? [])
  return props.categories.filter((c) => members.has(c.label)).sort((a, b) => b.count - a.count)
})

function pathStyle(line: MapLine, extra = ""): string {
  return `d: path('${line.path}');${extra}`
}
</script>

<template>
  <div ref="root" class="ws-linemap" :class="{ 'is-dark': isDark }" @keydown="onLabelsKeydown">
    <div class="ws-linemap__total">
      全部 <span class="num">{{ formatNumber(total) }}</span> 条
    </div>

    <svg
      ref="svg"
      class="ws-linemap__svg"
      :width="layout.width"
      :height="layout.height"
      :viewBox="`0 0 ${layout.width} ${layout.height}`"
      role="img"
      :aria-label="ariaLabel"
    >
      <!-- 没有结果时：只有枢纽和一条虚线 -->
      <path v-if="layout.emptyPath" :d="layout.emptyPath" class="ws-linemap__empty-line" />

      <!-- 失败：从枢纽出发的红色虚线，终点为空心圆 -->
      <g v-if="layout.failed" class="ws-linemap__failed" :style="{ opacity: hovered ? 0.2 : 1 }">
        <path :d="layout.failed.path" :style="`d: path('${layout.failed.path}')`" class="ws-linemap__failed-line" />
        <circle
          :cx="layout.terminalX"
          :cy="layout.failed.endY"
          :r="layout.failed.stationR"
          class="ws-linemap__failed-station"
        />
      </g>

      <g v-for="line in layout.lines" :key="line.key" class="ws-linemap__route" :style="{ opacity: lineOpacity(line) }">
        <!-- 低对比度的线路加 1 px 描边：先画一条宽 2 px 的描边色底线 -->
        <path
          v-if="styleOf(line).stroke"
          :d="line.path"
          class="ws-linemap__line ws-linemap__outline"
          :style="pathStyle(line, `stroke: ${styleOf(line).stroke}; stroke-width: ${line.width + 2}px;`)"
        />
        <path
          :d="line.path"
          :data-path="line.key"
          class="ws-linemap__line"
          :style="
            pathStyle(
              line,
              `stroke: ${styleOf(line).color}; stroke-width: ${line.width}px;${isDark ? ` filter: ${glowFilter(styleOf(line).color)};` : ''}`,
            )
          "
          @mouseenter="onEnter(line)"
          @mouseleave="onLeave"
        />
        <g class="ws-linemap__station-pos" :style="{ transform: `translate(${layout.terminalX}px, ${line.endY}px)` }">
          <circle
            :data-station="line.key"
            class="ws-linemap__station"
            cx="0"
            cy="0"
            :r="line.stationR"
            :style="{ stroke: styleOf(line).color }"
          />
        </g>
      </g>

      <!-- 枢纽：所有文本的出发点 -->
      <rect
        :x="layout.hub.x"
        :y="layout.hub.y"
        :width="layout.hub.width"
        :height="layout.hub.height"
        :rx="layout.hub.width / 2"
        class="ws-linemap__hub"
      />
    </svg>

    <p v-if="layout.emptyPath" class="ws-linemap__empty-text" :style="{ top: `${layout.emptyY - 34}px` }">
      {{ running ? "第一条结果到站后，线路会出现在这里" : "没有识别结果" }}
    </p>

    <!-- 终点标签：真实的可聚焦元素，屏幕阅读器可以逐条读到 -->
    <ul class="ws-linemap__labels" :style="{ left: `${layout.terminalX + 12}px` }">
      <li
        v-for="line in layout.lines"
        :key="line.key"
        class="ws-linemap__label-row"
        :data-label="line.key"
        :style="{ transform: `translateY(${line.endY - 16}px)` }"
      >
        <Popover v-if="line.key === OTHER_KEY" v-model:open="otherOpen" side="left" align="start" :width="280">
          <template #trigger>
            <button
              type="button"
              data-terminal
              class="ws-linemap__label"
              :class="{ 'is-selected': isSelected(line) }"
              :aria-label="`${line.label}，共 ${formatNumber(line.count)} 条，占 ${formatPercent(line.percent)}`"
              @mouseenter="onEnter(line)"
              @mouseleave="onLeave"
              @focus="hovered = line.key"
              @blur="hovered = null"
            >
              <span class="ws-linemap__name">{{ line.label }}</span>
              <AnimatedNumber class="ws-linemap__count" :value="line.count" />
              <span class="ws-linemap__pct num">{{ formatPercent(line.percent) }}</span>
            </button>
          </template>
          <p class="ws-linemap__other-title">{{ line.label }}，点击一项筛选结果表</p>
          <ul class="ws-linemap__other-list">
            <li v-for="m in otherMembers" :key="m.label">
              <button
                type="button"
                class="ws-linemap__other-item"
                :class="{ 'is-selected': selectedSet.has(m.label) }"
                @click="emit('toggle', [m.label], $event.shiftKey)"
              >
                <span class="ws-linemap__name">{{ m.label }}</span>
                <span class="num">{{ formatNumber(m.count) }}</span>
                <span class="ws-linemap__pct num">{{ formatPercent(m.percent) }}</span>
              </button>
            </li>
          </ul>
        </Popover>
        <button
          v-else
          type="button"
          data-terminal
          class="ws-linemap__label"
          :class="{ 'is-selected': isSelected(line) }"
          :aria-pressed="isSelected(line)"
          :aria-label="`${line.label}，共 ${formatNumber(line.count)} 条，占 ${formatPercent(line.percent)}`"
          @click="onLabelClick(line, $event)"
          @mouseenter="onEnter(line)"
          @mouseleave="onLeave"
          @focus="hovered = line.key"
          @blur="hovered = null"
        >
          <span class="ws-linemap__name">{{ line.label }}</span>
          <AnimatedNumber
            class="ws-linemap__count"
            :value="line.count"
            :from="freshKeys.has(line.key) ? 0 : undefined"
            :delay="freshKeys.has(line.key) ? DUR.line : 0"
          />
          <span class="ws-linemap__pct num">{{ formatPercent(line.percent) }}</span>
        </button>
      </li>
      <li
        v-if="layout.failed"
        class="ws-linemap__label-row is-failed"
        :style="{ transform: `translateY(${layout.failed.endY - 16}px)` }"
      >
        <span class="ws-linemap__label is-static">
          <span class="ws-linemap__name">未到站（失败）</span>
          <span class="ws-linemap__count num">{{ formatNumber(layout.failed.count) }}</span>
        </span>
        <button type="button" class="ws-linemap__view" data-terminal @click="emit('showFailed')">查看</button>
      </li>
    </ul>

    <!-- 悬停提示：条数、占比和 3 条示例原文 -->
    <div
      v-if="tipFor"
      class="ws-linemap__tip"
      role="tooltip"
      :style="{ top: `${tipFor.endY + 18}px`, right: `${layout.width - layout.terminalX + 12}px` }"
    >
      <p class="ws-linemap__tip-title">
        {{ tipFor.label }} <span class="num">{{ formatNumber(tipFor.count) }}</span> 条（{{ formatPercent(tipFor.percent) }}）
      </p>
      <template v-if="tipFor.key !== OTHER_KEY">
        <p v-if="samples.get(tipFor.label) === 'loading'" class="ws-linemap__tip-muted">正在取示例原文</p>
        <ul v-else-if="Array.isArray(samples.get(tipFor.label))" class="ws-linemap__tip-list">
          <li v-for="(s, i) in samples.get(tipFor.label) as string[]" :key="i">{{ clip(s, 60) }}</li>
        </ul>
      </template>
      <p v-else class="ws-linemap__tip-muted">包括 {{ tipFor.members.slice(0, 6).join("、") }}{{ tipFor.members.length > 6 ? " 等" : "" }}</p>
    </div>
  </div>
</template>

<style scoped>
.ws-linemap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 200px;
}

.ws-linemap__total {
  position: absolute;
  top: 8px;
  left: 8px;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-linemap__total .num {
  color: var(--ink);
  font-weight: 700;
}

.ws-linemap__svg {
  display: block;
  overflow: visible;
}

.ws-linemap__route {
  transition: opacity var(--dur-fast) var(--ease-out);
}

.ws-linemap__line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  cursor: pointer;
  transition:
    d var(--dur-slow) var(--ease-move),
    stroke-width var(--dur-number) var(--ease-move);
}

.ws-linemap__outline {
  pointer-events: none;
}

.ws-linemap__station-pos {
  transition: transform var(--dur-slow) var(--ease-move);
}

.ws-linemap__station {
  fill: var(--surface);
  stroke-width: 3;
  transform-box: fill-box;
  transform-origin: center;
  transition: r var(--dur-number) var(--ease-move);
}

.ws-linemap__hub {
  fill: var(--surface);
  stroke: var(--ink);
  stroke-width: 3;
}

.ws-linemap__empty-line {
  fill: none;
  stroke: var(--border-strong);
  stroke-width: 3;
  stroke-dasharray: 6 6;
  stroke-linecap: round;
}

.ws-linemap__empty-text {
  position: absolute;
  left: 72px;
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-linemap__failed {
  transition: opacity var(--dur-fast) var(--ease-out);
}

.ws-linemap__failed-line {
  fill: none;
  stroke: var(--status-danger);
  stroke-width: 3;
  stroke-dasharray: 6 6;
  stroke-linecap: butt;
  transition: d var(--dur-slow) var(--ease-move);
}

.ws-linemap__failed-station {
  fill: var(--surface);
  stroke: var(--status-danger);
  stroke-width: 2.5;
}

.ws-linemap__labels {
  position: absolute;
  top: 0;
  right: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-linemap__label-row {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 32px;
  transition: transform var(--dur-slow) var(--ease-move);
}

.ws-linemap__label {
  display: grid;
  grid-template-columns: minmax(0, 132px) 52px 48px;
  align-items: center;
  gap: var(--space-1);
  height: 32px;
  padding: 0 var(--space-1);
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--ink);
  text-align: left;
}

.ws-linemap__label:hover {
  background: var(--surface-2);
}

.ws-linemap__label.is-selected {
  outline: 2px solid var(--ink);
  outline-offset: 0;
}

.ws-linemap__label.is-static {
  cursor: default;
  background: transparent;
  grid-template-columns: minmax(0, 132px) 52px;
}

.ws-linemap__name {
  overflow: hidden;
  font-size: var(--text-base);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-linemap__count {
  font-size: 20px;
  font-weight: 700;
  text-align: right;
}

.ws-linemap__pct {
  color: var(--ink-2);
  font-size: var(--text-sm);
  text-align: right;
}

.ws-linemap__label-row.is-failed .ws-linemap__name,
.ws-linemap__label-row.is-failed .ws-linemap__count {
  color: var(--status-danger);
}

.ws-linemap__view {
  padding: 2px 6px;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--ink);
  font-size: var(--text-sm);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.ws-linemap__tip {
  position: absolute;
  z-index: var(--z-dropdown);
  width: 280px;
  padding: var(--space-3);
  border-radius: var(--radius-popover);
  background: var(--ink);
  color: var(--on-ink);
  box-shadow: var(--float-shadow);
  font-size: var(--text-sm);
  pointer-events: none;
  animation: ws-pop-in var(--dur-fast) var(--ease-out);
}

.ws-linemap__tip-title {
  margin: 0 0 var(--space-2);
  font-weight: 500;
}

.ws-linemap__tip-muted {
  margin: 0;
  opacity: 0.75;
}

.ws-linemap__tip-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding-left: 1.2em;
  list-style: disc;
  opacity: 0.9;
}

.ws-linemap__other-title {
  margin: 0 0 var(--space-2);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-linemap__other-list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-linemap__other-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 56px 56px;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  height: 32px;
  padding: 0 var(--space-2);
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--ink);
  text-align: left;
}

.ws-linemap__other-item:hover {
  background: var(--surface-2);
}

.ws-linemap__other-item.is-selected {
  outline: 2px solid var(--ink);
}

@media (prefers-reduced-motion: reduce) {
  .ws-linemap__line,
  .ws-linemap__station-pos,
  .ws-linemap__label-row,
  .ws-linemap__failed-line {
    transition-duration: 0ms;
  }
}
</style>
