<script setup lang="ts">
// 第三站“设任务”：任务类型、提示词、模型、并发、处理条数、起始行、相同文本只调用一次、更多选项。
// 切换任务类型时，提示词、模型、并发跟着换成该类型的默认值（用户手动改过的不覆盖）。
import { List, Split } from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import type { TaskType } from "@/api/types"
import { TASK_TYPE_LABEL } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Collapsible from "@/components/base/Collapsible.vue"
import FieldRow from "@/components/base/FieldRow.vue"
import Input from "@/components/base/Input.vue"
import NumberInput from "@/components/base/NumberInput.vue"
import Popover from "@/components/base/Popover.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Select from "@/components/base/Select.vue"
import Slider from "@/components/base/Slider.vue"
import Switch from "@/components/base/Switch.vue"
import type { SelectOption } from "@/components/base/types"
import { useModelsStore } from "@/stores/models"
import { useNewJobStore, type LimitMode } from "@/stores/newJob"
import { usePromptsStore } from "@/stores/prompts"
import { useSettingsStore } from "@/stores/settings"
import { formatDurationMs, formatNumber } from "@/utils/format"

const props = defineProps<{ register: (fn?: () => void) => void }>()

const router = useRouter()
const store = useNewJobStore()
const prompts = usePromptsStore()
const models = useModelsStore()
const settings = useSettingsStore()
const moreOpen = ref(false)

const TYPES: { value: TaskType; title: string; desc: string; icon: typeof Split }[] = [
  { value: "classify", title: "意图识别", desc: "判断每条文本属于哪个意图", icon: Split },
  { value: "summarize", title: "文本摘要", desc: "为每条文本写摘要", icon: List },
]

function onTypeKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "ArrowUp" && event.key !== "ArrowDown") return
  event.preventDefault()
  const next: TaskType = store.taskType === "classify" ? "summarize" : "classify"
  store.setTaskType(next)
  ;(document.querySelector(`[data-task-type="${next}"]`) as HTMLElement | null)?.focus()
}

const promptOptions = computed<SelectOption[]>(() =>
  prompts.byType(store.taskType).map((p) => ({
    value: String(p.id),
    label: `${p.name}  v${p.version}`,
    hint: p.is_default ? "默认" : p.is_builtin ? "内置" : undefined,
  })),
)

const promptModel = computed({
  get: () => (store.promptId === null ? undefined : String(store.promptId)),
  set: (value: string | undefined) => {
    if (value) store.setPrompt(Number(value))
  },
})

const currentPrompt = computed(() => prompts.byId(store.promptId))

const modelOptions = computed<SelectOption[]>(() => {
  const list = [...models.visible]
  const current = models.byId(store.modelId)
  if (current && !list.includes(current)) list.unshift(current)
  return list.map((m) => {
    const latency = m.avg_latency_ms ?? m.last_test?.latency_ms ?? null
    return {
      value: String(m.id),
      label: m.enabled ? m.name : `${m.name}（已停用）`,
      description: m.model,
      hint: latency !== null ? formatDurationMs(latency) : undefined,
      disabled: !m.enabled,
    }
  })
})

const modelModel = computed({
  get: () => (store.modelId === null ? undefined : String(store.modelId)),
  set: (value: string | undefined) => {
    if (value) store.setModel(Number(value))
  },
})

const hasEnabledModel = computed(() => models.items.some((m) => m.enabled))

const concurrencyModel = computed({
  get: () => store.concurrency,
  set: (value: number) => store.setConcurrency(value),
})

const totalRows = computed(() => store.preview?.total_rows ?? 0)

const limitModel = computed({
  get: () => store.limitMode,
  set: (value: string) => {
    store.limitMode = value as LimitMode
    if (value === "custom" && !store.customLimit) store.customLimit = 500
  },
})

const firstDataRow = computed(() => (store.isLines ? 1 : store.headerRow + 1))

const retriesModel = computed({
  get: () => store.maxRetries,
  set: (value: number | null) => {
    store.maxRetries = value ?? 0
  },
})
const defaultConcurrency = computed(() => settings.defaultConcurrency(store.taskType))
const canNext = computed(() => store.buildBody() !== null && hasEnabledModel.value)

// 参数变化后 300 ms 重新预估（“本次能省 N 次调用”来自预估接口）
let timer: number | undefined
watch(
  () => JSON.stringify(store.buildBody()),
  () => {
    window.clearTimeout(timer)
    timer = window.setTimeout(() => void store.refreshEstimate(), 300)
  },
  { immediate: true },
)

function next() {
  if (canNext.value) store.step = 3
}

function editPrompt() {
  if (store.promptId !== null) void router.push(`/prompts/${store.promptId}`)
}

onMounted(() => {
  store.applyDefaults()
  props.register(next)
})

onBeforeUnmount(() => {
  window.clearTimeout(timer)
  props.register(undefined)
})
</script>

<template>
  <div class="ws-task">
    <FieldRow label="任务类型" align="start">
      <div class="ws-task__types" role="radiogroup" aria-label="任务类型" @keydown="onTypeKeydown">
        <button
          v-for="t in TYPES"
          :key="t.value"
          type="button"
          role="radio"
          class="ws-task__type"
          :class="{ 'is-active': store.taskType === t.value }"
          :aria-checked="store.taskType === t.value"
          :tabindex="store.taskType === t.value ? 0 : -1"
          :data-task-type="t.value"
          @click="store.setTaskType(t.value)"
        >
          <span class="ws-task__type-title">
            <component :is="t.icon" :size="18" :stroke-width="1.75" aria-hidden="true" />
            {{ t.title }}
          </span>
          <span class="ws-task__type-desc">{{ t.desc }}</span>
        </button>
      </div>
    </FieldRow>

    <FieldRow label="提示词">
      <div class="ws-task__inline">
        <Select v-model="promptModel" :options="promptOptions" aria-label="提示词" width="300px" />
        <Popover side="bottom" align="start" :width="520">
          <template #trigger>
            <Button variant="text" size="sm" :disabled="!currentPrompt">查看</Button>
          </template>
          <div v-if="currentPrompt" class="ws-task__prompt">
            <p class="ws-task__prompt-title">{{ currentPrompt.name }} v{{ currentPrompt.version }}</p>
            <p class="ws-task__prompt-label">系统提示词</p>
            <pre class="ws-task__prompt-text mono">{{ currentPrompt.system_prompt }}</pre>
            <p class="ws-task__prompt-label">用户消息模板</p>
            <pre class="ws-task__prompt-text mono">{{ currentPrompt.user_template }}</pre>
          </div>
        </Popover>
        <Button variant="text" size="sm" :disabled="!currentPrompt" @click="editPrompt">编辑</Button>
      </div>
    </FieldRow>

    <FieldRow label="模型" :hint="hasEnabledModel ? undefined : '还没有可用的模型'">
      <div class="ws-task__inline">
        <Select v-model="modelModel" :options="modelOptions" aria-label="模型" width="360px" />
        <Button v-if="!hasEnabledModel" variant="text" size="sm" @click="router.push(models.connectRealModelRoute)">去接入模型</Button>
      </div>
    </FieldRow>

    <FieldRow label="并发" align="start">
      <div class="ws-task__slider">
        <Slider
          v-model="concurrencyModel"
          :min="1"
          :max="settings.limits.max_concurrency"
          :step="1"
          :ticks="[1, 5, 10, 15, 20]"
          :default-value="defaultConcurrency"
          aria-label="并发"
        />
        <span class="ws-task__value num">{{ store.concurrency }}</span>
      </div>
    </FieldRow>

    <FieldRow label="处理条数" align="start">
      <div class="ws-task__limit">
        <div class="ws-task__inline">
          <SegmentedControl
            v-model="limitModel"
            aria-label="处理条数"
            :options="[
              { value: '100', label: '100' },
              { value: 'custom', label: '自定义' },
              { value: 'all', label: `全部 ${formatNumber(totalRows)}` },
            ]"
          />
          <NumberInput
            v-if="store.limitMode === 'custom'"
            v-model="store.customLimit"
            :min="1"
            :max="settings.limits.max_rows_per_source"
            :width="120"
            unit="条"
            aria-label="自定义处理条数"
          />
        </div>
        <div class="ws-task__inline ws-task__start">
          <span>从第</span>
          <NumberInput v-model="store.startRow" :min="1" :width="100" :placeholder="String(firstDataRow)" aria-label="起始行" />
          <span>行开始</span>
        </div>
      </div>
    </FieldRow>

    <FieldRow label="相同文本只调用一次">
      <div class="ws-task__inline">
        <Switch v-model="store.dedupe" aria-label="相同文本只调用一次" />
        <span v-if="store.dedupe && store.estimate" class="ws-task__muted">
          本次能省 <span class="num">{{ formatNumber(store.estimate.duplicate_count) }}</span> 次调用
        </span>
      </div>
    </FieldRow>

    <Collapsible v-model:open="moreOpen" title="更多选项" :summary="moreOpen ? undefined : '失败重试次数、任务名称'">
      <div class="ws-task__more">
        <FieldRow label="失败重试次数">
          <NumberInput v-model="retriesModel" :min="0" :max="5" :width="100" unit="次" aria-label="失败重试次数" />
        </FieldRow>
        <FieldRow label="任务名称">
          <Input v-model="store.customName" :placeholder="store.autoName" :maxlength="100" aria-label="任务名称" />
        </FieldRow>
      </div>
    </Collapsible>

    <div class="ws-task__actions">
      <span v-if="store.estimating" class="ws-task__muted">正在预估…</span>
      <Button variant="primary" :disabled="!canNext" @click="next">下一站：确认</Button>
    </div>
    <span class="sr-only">{{ TASK_TYPE_LABEL[store.taskType] }}</span>
  </div>
</template>

<style scoped>
.ws-task {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: var(--form-max);
}

.ws-task__types {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 260px));
  gap: var(--space-4);
}

.ws-task__type {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  padding: var(--space-4);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-panel);
  background: var(--surface);
  color: var(--ink);
  text-align: left;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.ws-task__type:hover {
  border-color: var(--ink-3);
}

.ws-task__type.is-active {
  border-color: var(--ink);
  box-shadow: inset 0 0 0 1px var(--ink);
}

.ws-task__type-title {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-md);
  font-weight: 500;
}

.ws-task__type-desc {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-task__inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ws-task__slider {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  max-width: 520px;
}

.ws-task__value {
  min-width: 32px;
  padding-top: 2px;
  font-size: var(--text-lg);
  font-weight: 700;
  text-align: right;
}

.ws-task__limit {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-task__start {
  color: var(--ink-2);
}

.ws-task__muted {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-task__more {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 560px;
}

.ws-task__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-4);
}

.ws-task__prompt-title {
  margin: 0 0 var(--space-3);
  font-weight: 500;
}

.ws-task__prompt-label {
  margin: var(--space-3) 0 var(--space-1);
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-task__prompt-text {
  max-height: 220px;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  overflow: auto;
  border-radius: var(--radius-control);
  background: var(--surface-2);
  font-size: 12.5px;
  white-space: pre-wrap;
}
</style>
