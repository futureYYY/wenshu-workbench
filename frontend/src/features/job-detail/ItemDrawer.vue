<script setup lang="ts">
// 条目详情抽屉（06 第 6.6 节）：结果、原文、发送内容、原始输出、思考过程（没有时不显示）、尝试记录。
// 失败的条目默认打开“尝试记录”，顶部一句话写清原因和建议；截断的条目在“原文”顶部提示省略了多少字。
// J / K 或 ↑ / ↓ 切换上一条、下一条（按当前筛选和排序）；R 重新处理；E 修正意图；Esc 关闭。
// 人工复核：意图只能改成提示词里列出的类别（labelOptions），修正后同时显示模型原来的类别；可以撤销；
// “标记已复核”随时可切换。都是乐观更新，接口失败时回滚（06 第 7.2 节）。
import { ArrowDown, ArrowUp, Check, CircleCheck, Copy, Pencil, RotateCcw } from "@lucide/vue"
import { computed, nextTick, ref, watch } from "vue"
import { itemsApi } from "@/api/endpoints"
import type { ItemDetail, ItemSummary, TaskType } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Drawer from "@/components/base/Drawer.vue"
import DropdownMenu from "@/components/base/DropdownMenu.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import IconButton from "@/components/base/IconButton.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import StatusChip from "@/components/base/StatusChip.vue"
import Tabs from "@/components/base/Tabs.vue"
import type { MenuItem } from "@/components/base/types"
import JsonView from "@/components/editor/JsonView.vue"
import LineBadge from "@/components/metro/LineBadge.vue"
import StationDot from "@/components/metro/StationDot.vue"
import { useShortcut } from "@/composables/useShortcuts"
import { copyText } from "@/utils/download"
import { failureSentence } from "@/utils/errors"
import {
  formatConfidence,
  formatDateTime,
  formatDurationMs,
  formatNumber,
  formatRatio,
} from "@/utils/format"
import { renderMarkdown } from "@/utils/markdown"
import { extractOmittedChars } from "@/utils/text"
import { notify, notifyError } from "@/utils/toast"

const props = defineProps<{
  jobId: number
  itemId: number | null
  taskType: TaskType
  colorOf: (label: string) => number
  /** 提示词里列出的意图类别（Job.label_options），人工修正只能改成这些 */
  labelOptions: string[]
  /** 实时更新到达时递增，抽屉重新拉取详情 */
  refreshKey: number
}>()

const emit = defineEmits<{
  close: []
  navigate: [delta: number]
  read: [itemId: number]
  /** 人工修正、复核标记保存后，结果表更新这一行 */
  updated: [item: ItemSummary]
}>()

const NO_LABELS_TEXT = "这个任务的提示词没有按“- 类别名：说明”列出意图类别，不能人工修正。"


const open = computed({
  get: () => props.itemId !== null,
  set: (value: boolean) => {
    if (!value) emit("close")
  },
})

const detail = ref<ItemDetail | null>(null)
const loading = ref(false)
const loadError = ref<unknown>(null)
const tab = ref("result")
const rerunning = ref(false)
let seq = 0
let editPending = false      // 从结果表按 E 打开时，等详情加载完再打开“修改意图”菜单

async function load(keepTab = false) {
  const id = props.itemId
  if (id === null) return
  const mySeq = ++seq
  loading.value = true
  try {
    const item = await itemsApi.get(props.jobId, id)
    if (mySeq !== seq) return
    detail.value = item
    loadError.value = null
    if (!keepTab) tab.value = item.status === "failed" ? "attempts" : "result"
    if (tab.value === "reasoning" && !item.reasoning) tab.value = "result"
    maybeOpenPicker()
  } catch (e) {
    if (mySeq === seq) {
      loadError.value = e
      editPending = false
    }
  } finally {
    if (mySeq === seq) loading.value = false
  }
}

watch(
  () => props.itemId,
  (id) => {
    if (id === null) return
    detail.value = null
    void load(false)
  },
  { immediate: true },
)

watch(
  () => props.refreshKey,
  () => {
    if (props.itemId !== null) void load(true)
  },
)

const tabs = computed(() => [
  { value: "result", label: "结果" },
  { value: "input", label: "原文" },
  { value: "messages", label: "发送内容" },
  { value: "raw", label: "原始输出" },
  { value: "reasoning", label: "思考过程", hidden: !detail.value?.reasoning },
  { value: "attempts", label: "尝试记录" },
])

// 截断时省略的字数：用接口的 omitted_chars（04 第 8 节）；没有时再从发送内容里的省略标记读取
const omitted = computed(() => {
  const d = detail.value
  if (!d?.truncated) return null
  if (d.omitted_chars !== null) return d.omitted_chars
  for (const m of d.messages) {
    const n = extractOmittedChars(m.content)
    if (n !== null) return n
  }
  return null
})

// 有效摘要：人工修改过的取修改后的（修改在对照阅读里做）
const summaryHtml = computed(() => renderMarkdown(detail.value?.manual_summary ?? detail.value?.summary ?? ""))

const ROLE_LABEL: Record<string, string> = { system: "系统", user: "用户", assistant: "助手" }

async function copyMessage(content: string) {
  if (await copyText(content)) notify("已复制")
}

async function rerun() {
  const d = detail.value
  if (!d || rerunning.value) return
  rerunning.value = true
  try {
    await itemsApi.rerun(props.jobId, d.id)
    notify("已重新排队")
    await load(true)
  } catch (e) {
    notifyError(e)
  } finally {
    rerunning.value = false
  }
}

const canRerun = computed(() => {
  const s = detail.value?.status
  return s === "succeeded" || s === "failed"
})

// ---- 人工复核（06 第 6.6 节） ----
const pickerOpen = ref(false)
const savingLabel = ref(false)
const savingReviewed = ref(false)

const canCorrect = computed(() => props.taskType === "classify" && detail.value?.status === "succeeded")

const pickerItems = computed<MenuItem[]>(() => {
  const d = detail.value
  if (!d) return []
  const items: MenuItem[] = [{ heading: true, label: "改成提示词里列出的类别" }]
  for (const label of props.labelOptions) {
    items.push({
      key: `label-${label}`,
      label: label === d.label ? `${label}（模型识别）` : label,
      icon: label === d.effective_label ? Check : undefined,
      onSelect: () => void applyLabel(label),
    })
  }
  if (d.manual_label) {
    items.push({ separator: true, label: "" }, { key: "revert", label: "撤销修正", icon: RotateCcw, onSelect: () => void applyLabel(null) })
  }
  return items
})

/** E：打开“修改意图”菜单；从结果表按 E 时详情可能还没加载，加载完再打开 */
function startEdit() {
  editPending = true
  maybeOpenPicker()
}

function maybeOpenPicker() {
  const d = detail.value
  if (!editPending || !d || d.id !== props.itemId) return
  editPending = false
  if (!canCorrect.value) {
    if (props.taskType === "classify") notify("只有处理成功的条目可以人工修正")
    return
  }
  if (props.labelOptions.length === 0) {
    notify(NO_LABELS_TEXT)
    return
  }
  tab.value = "result"
  void nextTick(() => {
    pickerOpen.value = true
  })
}

/** 改成某个类别；改成模型原来的类别或传 null 都是撤销修正 */
async function applyLabel(label: string | null) {
  const d = detail.value
  if (!d || savingLabel.value) return
  const manual = label === null || label === d.label ? null : label
  if (manual === d.manual_label) return
  detail.value = {
    ...d,
    manual_label: manual,
    effective_label: manual ?? d.label,
    corrected: manual !== null,
    reviewed: manual !== null ? true : d.reviewed,
  }
  savingLabel.value = true
  try {
    const saved = await itemsApi.update(props.jobId, d.id, { manual_label: manual })
    emit("updated", saved)
    if (detail.value?.id === d.id) await load(true)
  } catch (e) {
    if (detail.value?.id === d.id) detail.value = d
    notifyError(e)
  } finally {
    savingLabel.value = false
  }
}

async function toggleReviewed() {
  const d = detail.value
  if (!d || savingReviewed.value) return
  const reviewed = !d.reviewed
  detail.value = { ...d, reviewed }
  savingReviewed.value = true
  try {
    const saved = await itemsApi.update(props.jobId, d.id, { reviewed })
    emit("updated", saved)
  } catch (e) {
    if (detail.value?.id === d.id) detail.value = { ...detail.value, reviewed: d.reviewed }
    notifyError(e)
  } finally {
    savingReviewed.value = false
  }
}

useShortcut(["j", "arrowdown"], () => emit("navigate", 1), { when: () => open.value })
useShortcut(["k", "arrowup"], () => emit("navigate", -1), { when: () => open.value })
useShortcut("r", () => void rerun(), { when: () => open.value && canRerun.value })
useShortcut("e", () => startEdit(), { when: () => open.value && props.taskType === "classify" && !pickerOpen.value })

defineExpose({ startEdit })
</script>

<template>
  <Drawer v-model:open="open" :width="640" :title="detail ? `第 ${detail.row_number} 行` : '条目详情'">
    <template #title>
      <span class="ws-item__title">
        <span>第 <span class="num">{{ detail?.row_number ?? "…" }}</span> 行</span>
        <StatusChip v-if="detail" :status="detail.status" kind="item" />
      </span>
    </template>
    <template #actions>
      <IconButton label="上一条" shortcut="k" @click="emit('navigate', -1)"><ArrowUp :size="16" :stroke-width="1.75" /></IconButton>
      <IconButton label="下一条" shortcut="j" @click="emit('navigate', 1)"><ArrowDown :size="16" :stroke-width="1.75" /></IconButton>
      <Button
        size="sm"
        variant="secondary"
        class="ws-item__review"
        :class="{ 'is-on': detail?.reviewed }"
        :disabled="!detail"
        :aria-pressed="detail?.reviewed ? 'true' : 'false'"
        data-testid="toggle-reviewed"
        @click="toggleReviewed"
      >
        <template #icon><CircleCheck :size="14" :stroke-width="1.75" /></template>
        {{ detail?.reviewed ? "已复核" : "标记已复核" }}
      </Button>
      <Button size="sm" variant="secondary" :disabled="!canRerun" :loading="rerunning" @click="rerun">
        <template #icon><RotateCcw :size="14" :stroke-width="1.75" /></template>
        重新处理
      </Button>
    </template>

    <div v-if="loading && !detail" class="ws-item__skeleton">
      <Skeleton height="20px" width="40%" />
      <Skeleton height="16px" />
      <Skeleton height="16px" width="80%" />
    </div>
    <EmptyState v-else-if="loadError && !detail" tone="danger" title="详情没有加载出来" :description="(loadError as Error).message" compact>
      <Button variant="primary" @click="load(true)">重新加载</Button>
    </EmptyState>

    <template v-else-if="detail">
      <Tabs v-model="tab" :items="tabs" id-prefix="item-tab" aria-label="条目详情" />

      <!-- 结果 -->
      <section v-if="tab === 'result'" class="ws-item__panel" role="tabpanel" aria-labelledby="item-tab-result">
        <p v-if="detail.status === 'failed'" class="ws-item__failure">{{ failureSentence(detail.error_code, detail.error_message) }}</p>
        <p v-else-if="detail.status === 'pending' || detail.status === 'running'" class="ws-item__muted">
          {{ detail.status === "running" ? "正在处理这一条" : "这一条还没有处理" }}
        </p>
        <p v-else-if="detail.status === 'skipped'" class="ws-item__muted">这一行的文本为空，已跳过</p>

        <dl v-if="taskType === 'classify' && detail.status === 'succeeded'" class="ws-item__dl">
          <dt>意图</dt>
          <dd class="ws-item__label-row">
            <LineBadge
              v-if="detail.effective_label"
              :label="detail.effective_label"
              :color-index="colorOf(detail.effective_label)"
              size="md"
            />
            <span v-if="detail.manual_label" class="ws-item__tag">人工修正</span>
            <DropdownMenu v-if="labelOptions.length" v-model:open="pickerOpen" :items="pickerItems" align="start">
              <template #trigger>
                <Button size="sm" variant="text" :loading="savingLabel" data-testid="correct-label">
                  <template #icon><Pencil :size="14" :stroke-width="1.75" /></template>
                  修改意图
                </Button>
              </template>
            </DropdownMenu>
          </dd>
          <template v-if="detail.manual_label">
            <dt>修正前</dt>
            <dd class="ws-item__label-row">
              <LineBadge v-if="detail.label" :label="detail.label" :color-index="colorOf(detail.label)" size="md" />
              <span class="ws-item__muted">
                模型识别<template v-if="detail.manual_at">，{{ formatDateTime(detail.manual_at) }} 人工修正</template>
              </span>
              <Button size="sm" variant="text" :disabled="savingLabel" @click="applyLabel(null)">撤销修正</Button>
            </dd>
          </template>
          <dt>置信度</dt>
          <dd class="num">{{ formatConfidence(detail.confidence) }}</dd>
          <dt>判断依据</dt>
          <dd>{{ detail.reason || "—" }}</dd>
        </dl>
        <p v-if="canCorrect && !labelOptions.length" class="ws-item__muted">{{ NO_LABELS_TEXT }}</p>

        <div v-if="taskType === 'summarize' && detail.status === 'succeeded'" class="ws-item__summary">
          <div class="ws-item__summary-text" v-html="summaryHtml" />
          <ol v-if="detail.key_points?.length" class="ws-item__points">
            <li v-for="(p, i) in detail.key_points" :key="i">
              <span>{{ p.text }}</span>
              <span v-if="p.sources.length" class="ws-item__sources num">[{{ p.sources.join("] [") }}]</span>
            </li>
          </ol>
          <p class="ws-item__muted">
            原文 <span class="num">{{ formatNumber(detail.input_chars) }}</span> 字，摘要
            <span class="num">{{ formatNumber(detail.output_chars) }}</span> 字，压缩
            <span class="num">{{ formatRatio(detail.compression_ratio) }}</span>
            <template v-if="detail.chunk_count > 1">，分 {{ detail.chunk_count }} 段摘要后合并</template>
          </p>
          <Button variant="secondary" size="sm" @click="emit('read', detail.id)">打开对照阅读</Button>
        </div>

        <dl class="ws-item__dl is-meta">
          <dt>耗时</dt>
          <dd>{{ detail.latency_ms !== null ? formatDurationMs(detail.latency_ms) : "—" }}</dd>
          <dt>tokens</dt>
          <dd class="num">
            <template v-if="detail.prompt_tokens !== null">{{ formatNumber(detail.prompt_tokens) }} + {{ formatNumber(detail.completion_tokens ?? 0) }}</template>
            <template v-else>—</template>
          </dd>
          <dt>模型</dt>
          <dd class="mono">{{ detail.model_used ?? "—" }}</dd>
          <dt>请求次数</dt>
          <dd class="num">{{ detail.attempts }}</dd>
          <template v-if="detail.dedup_of !== null">
            <dt>去重</dt>
            <dd>与另一条文本完全相同，复用了它的结果</dd>
          </template>
        </dl>
      </section>

      <!-- 原文 -->
      <section v-else-if="tab === 'input'" class="ws-item__panel" role="tabpanel" aria-labelledby="item-tab-input">
        <p v-if="detail.truncated" class="ws-item__warn">
          原文过长，识别时截去了中间<template v-if="omitted !== null"> {{ formatNumber(omitted) }} 字</template><template v-else>部分</template>
        </p>
        <p class="ws-item__reading">{{ detail.input_text }}</p>
      </section>

      <!-- 发送内容 -->
      <section v-else-if="tab === 'messages'" class="ws-item__panel" role="tabpanel" aria-labelledby="item-tab-messages">
        <p v-if="detail.chunk_count > 1" class="ws-item__muted">分段摘要时显示第一段的消息。</p>
        <div v-for="(m, i) in detail.messages" :key="i" class="ws-item__msg">
          <div class="ws-item__msg-head">
            <span class="ws-item__role">{{ ROLE_LABEL[m.role] ?? m.role }}</span>
            <IconButton label="复制" size="sm" @click="copyMessage(m.content)"><Copy :size="14" :stroke-width="1.75" /></IconButton>
          </div>
          <pre class="ws-item__msg-body mono">{{ m.content }}</pre>
        </div>
      </section>

      <!-- 原始输出 -->
      <section v-else-if="tab === 'raw'" class="ws-item__panel" role="tabpanel" aria-labelledby="item-tab-raw">
        <JsonView v-if="detail.raw_output" :value="detail.raw_output" raw />
        <p v-else class="ws-item__muted">还没有模型输出</p>
        <template v-if="detail.result">
          <p class="ws-item__label">解析结果</p>
          <JsonView :value="detail.result" />
        </template>
      </section>

      <!-- 思考过程 -->
      <section v-else-if="tab === 'reasoning'" class="ws-item__panel" role="tabpanel" aria-labelledby="item-tab-reasoning">
        <pre class="ws-item__reasoning">{{ detail.reasoning }}</pre>
      </section>

      <!-- 尝试记录 -->
      <section v-else class="ws-item__panel" role="tabpanel" aria-labelledby="item-tab-attempts">
        <p v-if="detail.status === 'failed'" class="ws-item__failure">{{ failureSentence(detail.error_code, detail.error_message) }}</p>
        <p v-if="detail.attempt_log.length === 0" class="ws-item__muted">还没有请求记录</p>
        <ol v-else class="ws-item__attempts">
          <li v-for="(a, i) in detail.attempt_log" :key="i" class="ws-item__attempt" :class="{ 'is-error': !!a.error_code }">
            <StationDot :size="12" :state="a.error_code ? 'error' : 'done'" />
            <div class="ws-item__attempt-body">
              <p class="ws-item__attempt-head">
                <span>第 <span class="num">{{ a.attempt }}</span> 次</span>
                <span class="ws-item__muted">{{ a.phase === "request" ? "普通请求" : a.phase === "parse_repair" ? "纠正输出格式" : a.phase === "merge" ? "合并各段摘要" : a.phase }}</span>
                <span v-if="a.status_code !== null" class="num ws-item__muted">HTTP {{ a.status_code }}</span>
                <span v-if="a.latency_ms !== null" class="num ws-item__muted">{{ formatDurationMs(a.latency_ms) }}</span>
                <span class="ws-item__muted ws-item__time">{{ formatDateTime(a.at) }}</span>
              </p>
              <p class="ws-item__attempt-msg" :class="{ 'is-error': !!a.error_code }">
                {{ a.message }}<span v-if="a.error_code" class="mono ws-item__code">{{ a.error_code }}</span>
              </p>
            </div>
          </li>
        </ol>
      </section>
    </template>
  </Drawer>
</template>

<style scoped>
.ws-item__title {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
}

.ws-item__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-item__panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding-top: var(--space-4);
}

.ws-item__failure {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--status-danger) 10%, transparent);
  color: var(--status-danger);
}

.ws-item__warn {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--status-warn) 12%, transparent);
  color: var(--status-warn);
  font-size: var(--text-sm);
}

.ws-item__muted {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-item__dl {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: var(--space-3) var(--space-4);
  margin: 0;
}

.ws-item__dl dt {
  color: var(--ink-2);
}

.ws-item__dl dd {
  margin: 0;
}

.ws-item__label-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
}

.ws-item__tag {
  padding: 0 8px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--ink-2);
  font-size: var(--text-xs);
  line-height: 20px;
}

.ws-item__review.is-on {
  border-color: var(--status-ok);
  color: var(--status-ok);
}

.ws-item__dl.is-meta {
  padding-top: var(--space-4);
  border-top: 1px solid var(--border);
  font-size: var(--text-sm);
}

.ws-item__summary {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.ws-item__summary-text {
  font-size: var(--text-lg);
  font-weight: 500;
  line-height: 1.6;
}

.ws-item__summary-text :deep(p) {
  margin: 0;
}

.ws-item__points {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding-left: 1.4em;
  list-style: decimal;
}

.ws-item__sources {
  margin-left: var(--space-2);
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-item__reading {
  max-width: var(--reading-max);
  margin: 0;
  font-size: var(--text-md);
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ws-item__msg {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ws-item__msg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ws-item__role {
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--ink-2);
  font-size: var(--text-xs);
  font-weight: 500;
}

.ws-item__msg-body,
.ws-item__reasoning {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--surface-2);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ws-item__reasoning {
  max-height: none;
  font-family: var(--font-sans);
  color: var(--ink-2);
}

.ws-item__label {
  margin: var(--space-2) 0 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-item__attempts {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-item__attempts::before {
  content: "";
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 4.5px;
  width: 3px;
  border-radius: var(--radius-pill);
  background: var(--border-strong);
}

.ws-item__attempt {
  position: relative;
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: var(--space-3);
}

.ws-item__attempt > :first-child {
  margin-top: 5px;
}

.ws-item__attempt-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ws-item__attempt-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-3);
  margin: 0;
}

.ws-item__time {
  margin-left: auto;
}

.ws-item__attempt-msg {
  margin: 0;
}

.ws-item__attempt-msg.is-error {
  color: var(--status-danger);
}

.ws-item__code {
  margin-left: var(--space-2);
  font-size: var(--text-xs);
  opacity: 0.8;
}
</style>
