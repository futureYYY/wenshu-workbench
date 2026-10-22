<script setup lang="ts">
// 新建任务（06 第 6.2 节）：顶部是站点步骤条，下面是当前站的内容；每一站的主按钮都在右下角，
// 按 Enter 等同于点击；Alt+← 回到上一站。?file=12 表示带着已上传的文件进入，?paste=1 打开粘贴文本。
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"
import MetroStepper from "@/components/metro/MetroStepper.vue"
import { useShortcut } from "@/composables/useShortcuts"
import { useFilesStore } from "@/stores/files"
import { useModelsStore } from "@/stores/models"
import { STEP_LABELS, useNewJobStore } from "@/stores/newJob"
import { usePromptsStore } from "@/stores/prompts"
import { useSettingsStore } from "@/stores/settings"
import { notifyError } from "@/utils/toast"
import StepConfirm from "./StepConfirm.vue"
import StepData from "./StepData.vue"
import StepFile from "./StepFile.vue"
import StepTask from "./StepTask.vue"

const route = useRoute()
const store = useNewJobStore()
const files = useFilesStore()
const settings = useSettingsStore()
const models = useModelsStore()
const prompts = usePromptsStore()

const fileTab = ref<"recent" | "paste">(route.query.paste === "1" ? "paste" : "recent")
const stepRefs = ref<{ primary?: () => void } | null>(null)

async function syncFromQuery() {
  const raw = route.query.file
  const id = typeof raw === "string" ? Number(raw) : NaN
  if (route.query.paste === "1") {
    fileTab.value = "paste"
    if (!Number.isFinite(id)) store.step = 0
  }
  if (Number.isFinite(id) && id > 0 && store.file?.id !== id) {
    try {
      const info = await files.get(id)
      await store.selectFile(info)
    } catch (e) {
      notifyError(e)
      store.step = 0
    }
  }
}

onMounted(async () => {
  await Promise.allSettled([settings.load(), models.load(), prompts.load()])
  store.applyDefaults()
  await syncFromQuery()
})

watch(
  () => [route.query.file, route.query.paste],
  () => void syncFromQuery(),
)

const canGoBack = computed(() => store.step > 0)

function go(index: number) {
  if (index < store.step) store.step = index
}

/** 当前站登记的主按钮动作（Enter 触发） */
function registerPrimary(fn: (() => void) | undefined) {
  stepRefs.value = { primary: fn }
}

function isEnterOwner(el: Element | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  if (el.isContentEditable) return true
  const tag = el.tagName
  if (tag === "TEXTAREA" || tag === "BUTTON" || tag === "A" || tag === "SELECT") return true
  return el.closest("[role='combobox'], [role='option'], [role='switch'], [role='tab'], [role='dialog'] [role='listbox'], .cm-editor") !== null
}

useShortcut(
  "enter",
  () => {
    const fn = stepRefs.value?.primary
    if (!fn) return false
    fn()
  },
  { allowInInput: true, when: () => !isEnterOwner(document.activeElement) },
)

useShortcut(
  "alt+arrowleft",
  () => {
    if (canGoBack.value) store.step -= 1
  },
  { allowInInput: true },
)
</script>

<template>
  <div class="ws-new">
    <div class="ws-new__stepper">
      <MetroStepper :steps="STEP_LABELS" :current="store.step" transition @go="go" />
    </div>

    <StepFile v-if="store.step === 0" v-model:tab="fileTab" :register="registerPrimary" />
    <StepData v-else-if="store.step === 1" :register="registerPrimary" />
    <StepTask v-else-if="store.step === 2" :register="registerPrimary" />
    <StepConfirm v-else :register="registerPrimary" />
  </div>
</template>

<style scoped>
.ws-new {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  max-width: 1280px;
  padding-top: var(--space-2);
}

.ws-new__stepper {
  max-width: 880px;
}
</style>
