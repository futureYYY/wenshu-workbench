<script setup lang="ts">
// 拖放层（06 第 6.11 节）：文件拖进窗口任意位置，出现遮罩和居中的大号始发站圆环，“松开，开始新任务”；
// 拖入的明显是图片、音频、视频（MIME 以 image/、audio/、video/ 开头）时圆环变为出错样式；其他一律放行，
// 交给上传接口按扩展名判断（不支持时返回 415，toast 说明）。松开后上传，进入“选数据”站。
// 拖到首页始发站这类自带拖放区域（data-dropzone）的地方时不显示遮罩，由那块区域自己表现。
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { UNSUPPORTED_MESSAGE, useFileIntake } from "@/composables/useFileIntake"
import { isObviouslyUnsupported, useFilesStore } from "@/stores/files"

const files = useFilesStore()
const { intakeFile } = useFileIntake()

const dragging = ref(false)
const overDropzone = ref(false)
const unsupported = ref(false)
let lastOver = 0
let watchdog: number | undefined

function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files")
}

function checkUnsupported(event: DragEvent): boolean {
  const items = Array.from(event.dataTransfer?.items ?? []).filter((i) => i.kind === "file")
  if (items.length === 0) return false
  return items.every((i) => isObviouslyUnsupported(i.type))
}

function stopWatchdog() {
  window.clearInterval(watchdog)
  watchdog = undefined
}

function hide() {
  dragging.value = false
  overDropzone.value = false
  unsupported.value = false
  stopWatchdog()
}

function onDragEnter(event: DragEvent) {
  if (!hasFiles(event)) return
  event.preventDefault()
  dragging.value = true
  unsupported.value = checkUnsupported(event)
  lastOver = Date.now()
  if (watchdog === undefined) {
    // 有的浏览器离开窗口时不发 dragleave：一段时间没有 dragover 就收起
    watchdog = window.setInterval(() => {
      if (Date.now() - lastOver > 400) hide()
    }, 200)
  }
}

function onDragOver(event: DragEvent) {
  if (!hasFiles(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = unsupported.value ? "none" : "copy"
  lastOver = Date.now()
  dragging.value = true
  const target = event.target instanceof Element ? event.target : null
  overDropzone.value = !!target?.closest("[data-dropzone]")
}

function onDragLeave(event: DragEvent) {
  // 离开窗口时 relatedTarget 为空
  if (!event.relatedTarget) hide()
}

async function onDrop(event: DragEvent) {
  if (!hasFiles(event)) return
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  const wasUnsupported = unsupported.value
  hide()
  if (!file || wasUnsupported) return
  await intakeFile(file)
}

onMounted(() => {
  window.addEventListener("dragenter", onDragEnter)
  window.addEventListener("dragover", onDragOver)
  window.addEventListener("dragleave", onDragLeave)
  window.addEventListener("drop", onDrop)
})

onBeforeUnmount(() => {
  window.removeEventListener("dragenter", onDragEnter)
  window.removeEventListener("dragover", onDragOver)
  window.removeEventListener("dragleave", onDragLeave)
  window.removeEventListener("drop", onDrop)
  stopWatchdog()
})

const visible = computed(() => (dragging.value && !overDropzone.value) || files.uploadingName !== null)
const progress = computed(() => files.uploadProgress)
const R = 52
const C = 2 * Math.PI * R
</script>

<template>
  <Transition name="ws-drop">
    <div v-if="visible" class="ws-drop" :class="{ 'is-error': unsupported && dragging }" aria-live="polite">
      <div class="ws-drop__center">
        <svg class="ws-drop__ring" width="128" height="128" viewBox="0 0 128 128" aria-hidden="true">
          <circle cx="64" cy="64" :r="R" class="ws-drop__track" :class="{ 'is-pending': progress !== null }" />
          <circle
            v-if="progress !== null"
            cx="64"
            cy="64"
            :r="R"
            class="ws-drop__arc"
            :stroke-dasharray="C"
            :stroke-dashoffset="C * (1 - progress)"
            transform="rotate(-90 64 64)"
          />
          <g v-if="unsupported && dragging" class="ws-drop__glyph">
            <line x1="64" y1="44" x2="64" y2="70" />
            <circle cx="64" cy="82" r="3.5" />
          </g>
        </svg>
        <p class="ws-drop__text">
          <template v-if="files.uploadingName">正在上传 {{ files.uploadingName }}</template>
          <template v-else-if="unsupported">{{ UNSUPPORTED_MESSAGE }}</template>
          <template v-else>松开，开始新任务</template>
        </p>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.ws-drop {
  position: fixed;
  inset: 0;
  z-index: var(--z-drop);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--overlay);
  pointer-events: none;
}

.ws-drop__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-10) var(--space-12);
  border-radius: var(--radius-drawer);
  background: var(--surface);
  box-shadow: var(--float-shadow);
}

.ws-drop__track {
  fill: var(--surface);
  stroke: var(--ink);
  stroke-width: 8;
}

.ws-drop__track.is-pending {
  stroke: var(--border-strong);
}

.ws-drop.is-error .ws-drop__track {
  stroke: var(--status-danger);
}

.ws-drop__arc {
  fill: none;
  stroke: var(--ink);
  stroke-width: 8;
  stroke-linecap: round;
  transition: stroke-dashoffset var(--dur-base) var(--ease-out);
}

.ws-drop__glyph line {
  stroke: var(--status-danger);
  stroke-width: 6;
  stroke-linecap: round;
}

.ws-drop__glyph circle {
  fill: var(--status-danger);
}

.ws-drop__text {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 500;
}

.ws-drop.is-error .ws-drop__text {
  color: var(--status-danger);
}

.ws-drop-enter-active,
.ws-drop-leave-active {
  transition: opacity var(--dur-fast) var(--ease-out);
}

.ws-drop-enter-from,
.ws-drop-leave-to {
  opacity: 0;
}
</style>
