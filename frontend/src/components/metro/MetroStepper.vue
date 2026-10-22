<script setup lang="ts">
// 站点步骤条（06 第 5.1 节）：线宽 4 px，已过的线段为墨色实线，未到的为虚线（6 实 4 空）；
// 站名在站点下方；已过站可点击回到该站；站与站之间移动时线段由左向右填充墨色（220 ms）。
// origin 用于首页的始发站：第一站 64 px，线宽 6 px，其余三个 16 px 的未到站点。
import StationDot from "./StationDot.vue"

const props = withDefaults(
  defineProps<{
    steps: readonly string[]
    current: number
    /** 第一站的上传进度（0–1） */
    progress?: number | null
    /** 拖入文件时整条线“准备发车”：从左到右填成墨色 */
    armed?: boolean
    origin?: boolean
    /** 始发站圆环的缩放（拖入时 1.08） */
    scale?: number
    /** 参与页面切换的 View Transitions（同一页面上只能有一个） */
    transition?: boolean
  }>(),
  { progress: null, armed: false, origin: false, scale: 1, transition: false },
)

const emit = defineEmits<{ go: [index: number] }>()

function stateOf(index: number): "todo" | "current" | "done" {
  if (props.origin) return index === 0 ? "current" : "todo"
  if (index < props.current) return "done"
  if (index === props.current) return "current"
  return "todo"
}

function sizeOf(index: number): 12 | 16 | 64 {
  if (props.origin) return index === 0 ? 64 : 16
  return index === props.current ? 16 : 12
}

function canGo(index: number): boolean {
  return !props.origin && index < props.current
}

/** 第 index 站到下一站之间的线段是否已填成墨色 */
function filled(index: number): boolean {
  return props.armed || (!props.origin && index < props.current)
}
</script>

<template>
  <ol
    class="ws-stepper"
    :class="{ 'is-origin': origin, 'is-armed': armed, 'has-transition': transition }"
    :style="{ gridTemplateColumns: `repeat(${Math.max(0, steps.length - 1)}, minmax(0, 1fr)) max-content` }"
    aria-label="新建任务步骤"
  >
    <li
      v-for="(label, i) in steps"
      :key="label"
      class="ws-stepper__stop"
      :class="`is-${stateOf(i)}`"
      :style="{ '--size': `${sizeOf(i)}px`, '--seg-delay': `${i * 90}ms` }"
      :aria-current="!origin && i === current ? 'step' : undefined"
    >
      <div class="ws-stepper__track">
        <span v-if="i < steps.length - 1" class="ws-stepper__seg" :class="{ 'is-filled': filled(i) }" aria-hidden="true">
          <span class="ws-stepper__fill" />
        </span>
        <button
          v-if="canGo(i)"
          type="button"
          class="ws-stepper__dot-btn"
          :aria-label="`回到“${label}”`"
          @click="emit('go', i)"
        >
          <StationDot :size="sizeOf(i)" :state="stateOf(i)" />
        </button>
        <StationDot
          v-else
          :size="sizeOf(i)"
          :state="stateOf(i)"
          :progress="i === 0 ? progress : null"
          :scale="origin && i === 0 ? scale : 1"
        />
      </div>
      <button v-if="canGo(i)" type="button" class="ws-stepper__label is-link" tabindex="-1" @click="emit('go', i)">
        {{ label }}
      </button>
      <span v-else class="ws-stepper__label">{{ label }}</span>
    </li>
  </ol>
</template>

<style scoped>
.ws-stepper {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-stepper.has-transition {
  view-transition-name: metro-line;
}

.ws-stepper__stop {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  min-width: 0;
}

.ws-stepper__track {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  height: 24px;
}

.ws-stepper.is-origin .ws-stepper__track {
  height: 64px;
}

/* 从本站的右边缘连到下一站的左边缘（下一站在下一列的起点） */
.ws-stepper__seg {
  position: absolute;
  top: 50%;
  left: var(--size);
  right: 0;
  height: 4px;
  margin-top: -2px;
  background-image: repeating-linear-gradient(to right, var(--border-strong) 0 6px, transparent 6px 10px);
  overflow: hidden;
}

.ws-stepper.is-origin .ws-stepper__seg {
  height: 6px;
  margin-top: -3px;
}

.ws-stepper__fill {
  display: block;
  width: 0;
  height: 100%;
  background: var(--ink);
  transition: width var(--dur-base) var(--ease-move);
}

.ws-stepper.is-armed .ws-stepper__fill {
  transition-duration: calc(var(--dur-slow) / 3);
  transition-delay: var(--seg-delay);
}

.ws-stepper__seg.is-filled .ws-stepper__fill {
  width: 100%;
}

.ws-stepper__dot-btn {
  display: inline-flex;
  padding: 0;
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
}

/* 未到站与已过站同为 13 px --ink-2、字重 400，靠站点样式和能否点击区分（06 第 5.1 节） */
.ws-stepper__label {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font-size: var(--text-sm);
  font-weight: 400;
  white-space: nowrap;
}

.ws-stepper__label.is-link {
  color: var(--ink-2);
}

.ws-stepper__label.is-link:hover {
  color: var(--ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.ws-stepper__stop.is-current .ws-stepper__label {
  color: var(--ink);
  font-size: var(--text-base);
  font-weight: 700;
}

.ws-stepper.is-origin .ws-stepper__label {
  color: var(--ink-2);
  font-size: var(--text-sm);
  font-weight: 400;
}

.ws-stepper.is-origin .ws-stepper__stop:first-child .ws-stepper__label {
  color: var(--ink);
  font-weight: 500;
}
</style>
