<script setup lang="ts">
// 始发站区域（06 第 6.1 节）：拖入文件就开始。
// 拖入时：描边变为 2 px 墨色，始发站圆环放大到 1.08 倍，线路从左到右填成墨色（准备发车）；
// 松开后：始发站圆环显示上传进度弧线（上传由全局拖放层统一处理）。
import { computed, ref, useTemplateRef } from "vue"
import Button from "@/components/base/Button.vue"
import MetroStepper from "@/components/metro/MetroStepper.vue"
import { useFileIntake } from "@/composables/useFileIntake"
import { FILE_ACCEPT, useFilesStore } from "@/stores/files"
import { STEP_LABELS } from "@/stores/newJob"

withDefaults(defineProps<{ compact?: boolean; showPaste?: boolean; transition?: boolean }>(), {
  compact: false,
  showPaste: true,
  transition: true,
})
const emit = defineEmits<{ paste: [] }>()

const files = useFilesStore()
const { intakeFile } = useFileIntake()
const input = useTemplateRef<HTMLInputElement>("input")
const depth = ref(0)
const armed = computed(() => depth.value > 0)
const busy = computed(() => files.uploadingName !== null)

const steps = ["始发站", ...STEP_LABELS.slice(1)]

function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files")
}

function onEnter(event: DragEvent) {
  if (hasFiles(event)) depth.value += 1
}

function onLeave(event: DragEvent) {
  if (hasFiles(event)) depth.value = Math.max(0, depth.value - 1)
}

function onDrop() {
  depth.value = 0
}

function choose() {
  input.value?.click()
}

async function onPicked(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ""
  if (file) await intakeFile(file)
}

defineExpose({ choose })
</script>

<template>
  <section
    class="ws-start"
    :class="{ 'is-armed': armed, 'is-compact': compact }"
    data-dropzone
    data-page-focus
    tabindex="-1"
    aria-label="始发站：把文件拖到这里，或选择文件"
    @dragenter="onEnter"
    @dragleave="onLeave"
    @drop="onDrop"
  >
    <MetroStepper
      :steps="steps"
      :current="0"
      origin
      :armed="armed"
      :scale="armed ? 1.08 : 1"
      :progress="files.uploadProgress"
      :transition="transition"
    />
    <div class="ws-start__copy">
      <h2 class="ws-start__title">
        <template v-if="busy">正在上传 {{ files.uploadingName }}</template>
        <template v-else>把文件拖到这里，开始一次意图识别或摘要</template>
      </h2>
      <p class="ws-start__desc">支持 txt、md、csv、xlsx、xls，单个文件不超过 50 MB</p>
    </div>
    <div class="ws-start__actions">
      <Button variant="primary" :loading="busy" data-testid="choose-file" @click="choose">选择文件</Button>
      <Button v-if="showPaste" variant="secondary" :disabled="busy" @click="emit('paste')">粘贴文本</Button>
      <span class="ws-start__tip">也可以按 Ctrl+V 直接粘贴</span>
    </div>
    <input
      ref="input"
      class="sr-only"
      type="file"
      :accept="FILE_ACCEPT"
      tabindex="-1"
      aria-hidden="true"
      data-testid="file-input"
      @change="onPicked"
    />
  </section>
</template>

<style scoped>
.ws-start {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  min-height: 300px;
  padding: var(--space-8) var(--space-10);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
  transition:
    border-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
  outline: none;
}

.ws-start.is-compact {
  min-height: 0;
  padding: var(--space-6) var(--space-8);
}

.ws-start.is-armed {
  border-color: var(--ink);
  box-shadow: inset 0 0 0 1px var(--ink);
}

.ws-start__copy {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ws-start__title {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 700;
  line-height: 1.3;
}

.ws-start.is-compact .ws-start__title {
  font-size: var(--text-xl);
}

.ws-start__desc {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-start__actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.ws-start__tip {
  color: var(--ink-2);
  font-size: var(--text-sm);
}
</style>
