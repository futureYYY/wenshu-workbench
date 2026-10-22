<script setup lang="ts">
// 提示词工坊右栏：试运行（06 第 6.7 节）。使用编辑器里的当前内容，不需要先保存；
// 运行中“运行”变为“停止”；显示原始输出（流式）、解析结果、耗时和 tokens；解析失败时写明原因。
import { PanelRightClose } from "@lucide/vue"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { ApiError } from "@/api/client"
import type { PlaygroundDone, PromptDraft, SampleRow, TaskType } from "@/api/types"
import { isSummarizeResult } from "@/api/types"
import { runPlayground } from "@/api/stream"
import Button from "@/components/base/Button.vue"
import IconButton from "@/components/base/IconButton.vue"
import Kbd from "@/components/base/Kbd.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Select from "@/components/base/Select.vue"
import Textarea from "@/components/base/Textarea.vue"
import type { SelectOption } from "@/components/base/types"
import LineBadge from "@/components/metro/LineBadge.vue"
import { useModelsStore } from "@/stores/models"
import { useSettingsStore } from "@/stores/settings"
import { formatConfidence, formatDurationMs, formatNumber } from "@/utils/format"
import { renderMarkdown } from "@/utils/markdown"
import SamplePicker from "./SamplePicker.vue"

const props = defineProps<{ taskType: TaskType; draft: PromptDraft }>()
const emit = defineEmits<{ collapse: [] }>()

const models = useModelsStore()
const settings = useSettingsStore()

const modelId = ref<string | undefined>(undefined)
const sampleKind = ref<"text" | "row">("text")
const sampleText = ref("")
const rowSample = ref<SampleRow | null>(null)
const rowText = ref("")
const pickerOpen = ref(false)

const running = ref(false)
const stageLabel = ref("")
const output = ref("")
const reasoning = ref("")
const done = ref<PlaygroundDone | null>(null)
const errorMessage = ref<string | null>(null)
let controller: AbortController | null = null

const modelOptions = computed<SelectOption[]>(() =>
  models.visible.map((m) => ({
    value: String(m.id),
    label: m.enabled ? m.name : `${m.name}（已停用）`,
    description: m.model,
    disabled: !m.enabled,
  })),
)

function pickDefaultModel() {
  const preferred = models.defaultFor(props.taskType)
  const fallback = models.visible.find((m) => m.enabled) ?? null
  const chosen = preferred && preferred.enabled ? preferred : fallback
  modelId.value = chosen ? String(chosen.id) : undefined
}

watch(
  () => [props.taskType, models.items.length, settings.settings?.default_model_id[props.taskType]],
  () => {
    const current = models.byId(Number(modelId.value))
    if (!current || !current.enabled) pickDefaultModel()
  },
  { immediate: true },
)

const sampleModel = computed({
  get: () => sampleKind.value as string,
  set: (value: string) => {
    sampleKind.value = value === "row" ? "row" : "text"
    if (value === "row" && !rowSample.value) pickerOpen.value = true
  },
})

const canRun = computed(() => {
  if (!modelId.value) return false
  return sampleKind.value === "text" ? sampleText.value.trim() !== "" : rowSample.value !== null
})

function onPick(sample: SampleRow, text: string) {
  rowSample.value = sample
  rowText.value = text
  sampleKind.value = "row"
}

async function run() {
  if (running.value) return
  if (!canRun.value || !modelId.value) {
    errorMessage.value = !modelId.value ? "先选择一个模型" : "先粘贴一段样本，或从文件里挑一行"
    return
  }
  controller = new AbortController()
  running.value = true
  stageLabel.value = ""
  output.value = ""
  reasoning.value = ""
  done.value = null
  errorMessage.value = null
  const sample = sampleKind.value === "text" ? { kind: "text" as const, text: sampleText.value } : (rowSample.value as SampleRow)
  try {
    await runPlayground(
      { prompt: props.draft, model_id: Number(modelId.value), sample },
      {
        onStage: (stage) => {
          if (stage.name === "chunk") stageLabel.value = `第 ${stage.index ?? 1}/${stage.total ?? 1} 段`
          else if (stage.name === "merge") stageLabel.value = "合并各段摘要"
          else stageLabel.value = ""
          // 每个阶段的输出单独显示
          output.value = ""
        },
        onDelta: (delta) => {
          output.value += delta.content
        },
        onReasoningDelta: (delta) => {
          reasoning.value += delta.content
        },
        onDone: (result) => {
          done.value = result
          output.value = result.raw_output
          if (result.reasoning) reasoning.value = result.reasoning
          stageLabel.value = ""
        },
        onError: (err) => {
          errorMessage.value = err.message
        },
      },
      controller.signal,
    )
  } catch (e) {
    errorMessage.value = e instanceof ApiError ? e.message : "试运行没有完成，请重试"
  } finally {
    running.value = false
    controller = null
  }
}

function stop() {
  controller?.abort()
}

onBeforeUnmount(stop)

defineExpose({ run, stop, running })

const parsedClassify = computed(() => {
  const p = done.value?.parsed
  return p && !isSummarizeResult(p) ? p : null
})

const parsedSummary = computed(() => {
  const p = done.value?.parsed
  return p && isSummarizeResult(p) ? p : null
})

const summaryHtml = computed(() => renderMarkdown(parsedSummary.value?.summary ?? ""))
</script>

<template>
  <aside class="ws-play" aria-label="试运行">
    <header class="ws-play__head">
      <h2 class="ws-play__title">试运行</h2>
      <IconButton label="收起试运行" size="sm" @click="emit('collapse')"><PanelRightClose :size="16" :stroke-width="1.75" /></IconButton>
    </header>

    <label class="ws-play__field">
      <span>模型</span>
      <Select v-model="modelId" :options="modelOptions" placeholder="选择模型" aria-label="试运行使用的模型" />
    </label>

    <div class="ws-play__field">
      <span>样本</span>
      <SegmentedControl
        v-model="sampleModel"
        size="sm"
        aria-label="样本来源"
        :options="[
          { value: 'text', label: '粘贴' },
          { value: 'row', label: '从文件选' },
        ]"
      />
    </div>

    <Textarea
      v-if="sampleKind === 'text'"
      v-model="sampleText"
      :rows="5"
      placeholder="粘贴一段要试的文本"
      aria-label="试运行样本"
      data-testid="playground-sample"
    />
    <div v-else class="ws-play__row">
      <pre class="ws-play__row-text">{{ rowText || "还没有挑选样本" }}</pre>
      <Button variant="text" size="sm" @click="pickerOpen = true">{{ rowSample ? "换一行" : "挑一行" }}</Button>
    </div>

    <div class="ws-play__run">
      <Button v-if="!running" variant="primary" :disabled="!canRun" data-testid="playground-run" @click="run">
        运行
        <span class="ws-play__keys"><Kbd inverse>Ctrl</Kbd><Kbd inverse>Enter</Kbd></span>
      </Button>
      <Button v-else variant="secondary" @click="stop">停止</Button>
      <span v-if="running" class="ws-play__stage">{{ stageLabel || "正在生成" }}</span>
    </div>

    <p v-if="errorMessage" class="ws-play__error" role="alert">{{ errorMessage }}</p>

    <section v-if="output || running" class="ws-play__section">
      <p class="ws-play__label">原始输出{{ running ? "（流式）" : "" }}</p>
      <pre class="ws-play__output mono" aria-live="polite" data-testid="playground-output">{{ output }}</pre>
    </section>

    <details v-if="reasoning" class="ws-play__reasoning">
      <summary>思考过程</summary>
      <pre>{{ reasoning }}</pre>
    </details>

    <section v-if="done" class="ws-play__section" data-testid="playground-result">
      <p class="ws-play__label">解析结果</p>
      <p v-if="done.parse_error" class="ws-play__error">输出无法解析：{{ done.parse_error }}</p>
      <div v-else-if="parsedClassify" class="ws-play__classify">
        <LineBadge :label="parsedClassify.label" :color-index="0" size="md" />
        <span v-if="parsedClassify.confidence !== null" class="num">{{ formatConfidence(parsedClassify.confidence) }}</span>
        <p v-if="parsedClassify.reason" class="ws-play__reason">{{ parsedClassify.reason }}</p>
      </div>
      <div v-else-if="parsedSummary" class="ws-play__summary">
        <div class="ws-play__summary-text" v-html="summaryHtml" />
        <ol v-if="parsedSummary.key_points.length">
          <li v-for="(p, i) in parsedSummary.key_points" :key="i">
            {{ p.text }}<span v-if="p.sources.length" class="ws-play__sources num"> [{{ p.sources.join("] [") }}]</span>
          </li>
        </ol>
      </div>
      <p class="ws-play__meta">
        <span>{{ formatDurationMs(done.latency_ms) }}</span>
        <span class="num">{{ formatNumber(done.usage.prompt_tokens) }} + {{ formatNumber(done.usage.completion_tokens) }}</span>
        <span v-if="done.chunk_count > 1">分 {{ done.chunk_count }} 段</span>
        <span v-if="done.truncated">原文过长，截去了中间部分</span>
      </p>
    </section>

    <SamplePicker v-model:open="pickerOpen" @pick="onPick" />
  </aside>
</template>

<style scoped>
.ws-play {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-play__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ws-play__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 500;
}

.ws-play__field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  color: var(--ink-2);
}

.ws-play__row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.ws-play__row-text {
  width: 100%;
  max-height: 140px;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--surface-2);
  font-family: var(--font-sans);
  white-space: pre-wrap;
}

.ws-play__run {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.ws-play__keys {
  display: inline-flex;
  gap: 2px;
  margin-left: var(--space-2);
}

.ws-play__stage {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-play__error {
  margin: 0;
  color: var(--status-danger);
  font-size: var(--text-sm);
}

.ws-play__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-play__label {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-play__output {
  max-height: 260px;
  min-height: 48px;
  margin: 0;
  padding: var(--space-3);
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--surface-2);
  font-size: 12.5px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ws-play__reasoning summary {
  color: var(--ink-2);
  font-size: var(--text-sm);
  cursor: pointer;
}

.ws-play__reasoning pre {
  max-height: 200px;
  margin: var(--space-2) 0 0;
  overflow: auto;
  color: var(--ink-2);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  white-space: pre-wrap;
}

.ws-play__classify {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ws-play__reason {
  width: 100%;
  margin: 0;
  color: var(--ink-2);
}

.ws-play__summary-text {
  font-weight: 500;
}

.ws-play__summary-text :deep(p) {
  margin: 0 0 var(--space-2);
}

.ws-play__summary ol {
  margin: 0;
  padding-left: 1.4em;
  list-style: decimal;
}

.ws-play__sources {
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-play__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}
</style>
