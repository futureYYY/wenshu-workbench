<script setup lang="ts">
// 任务详情（06 第 6.4、6.5 节）。
// 意图识别：运行中左边并行轨道、右边线网图；完成后轨道收起（360 ms），线网图展开成整宽，结果表在下方。
// 文本摘要：运行中左边并行轨道、右边浓缩计；完成后页头下方是浓缩计（合计），点击某行进入对照阅读。
import { Download, Pause, Play, RotateCcw, Search, Square, Trash2, X } from "@lucide/vue"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ApiError, itemsApi, jobsApi, systemApi } from "@/api/endpoints"
import type { ItemFilters, ItemOrder, ItemStatus, ItemSummary, Job } from "@/api/types"
import { TASK_TYPE_LABEL } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Dialog from "@/components/base/Dialog.vue"
import DropdownMenu from "@/components/base/DropdownMenu.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import Input from "@/components/base/Input.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Select from "@/components/base/Select.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import type { MenuItem, SegmentOption, SelectOption } from "@/components/base/types"
import DataGrid from "@/components/data/DataGrid.vue"
import CompressionGauge from "@/components/metro/CompressionGauge.vue"
import LineBadge from "@/components/metro/LineBadge.vue"
import LineMap from "@/components/metro/LineMap.vue"
import LineProgress from "@/components/metro/LineProgress.vue"
import ParallelTracks from "@/components/metro/ParallelTracks.vue"
import { hasResults, useJobActions } from "@/composables/useJobActions"
import { useJobLive } from "@/composables/useJobLive"
import { useShortcut } from "@/composables/useShortcuts"
import { useJobsStore } from "@/stores/jobs"
import { useUiStore } from "@/stores/ui"
import { formatNumber, formatRatio } from "@/utils/format"
import { pauseNotice } from "@/utils/pauseReason"
import { notify, notifyError } from "@/utils/toast"
import ItemDrawer from "./ItemDrawer.vue"

type StatusBucket = "all" | "succeeded" | "failed" | "skipped" | "pending"

const STATUS_FILTER: Record<StatusBucket, ItemStatus[]> = {
  all: [],
  succeeded: ["succeeded"],
  failed: ["failed"],
  skipped: ["skipped"],
  pending: ["pending", "running"],
}

// 人工复核的筛选（04 第 8.2 节的 corrected、reviewed 参数）
type ReviewBucket = "all" | "corrected" | "reviewed" | "unreviewed"

const REVIEW_FILTER: Record<ReviewBucket, Pick<ItemFilters, "corrected" | "reviewed">> = {
  all: {},
  corrected: { corrected: true },
  reviewed: { reviewed: true },
  unreviewed: { reviewed: false },
}

const REVIEW_OPTIONS: SelectOption[] = [
  { value: "all", label: "复核：全部" },
  { value: "corrected", label: "人工修正" },
  { value: "reviewed", label: "已复核" },
  { value: "unreviewed", label: "未复核" },
]

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const jobsStore = useJobsStore()

const jobId = computed<number | null>(() => {
  const n = Number(route.params.id)
  return Number.isFinite(n) && n > 0 ? n : null
})

const grid = useTemplateRef<InstanceType<typeof DataGrid>>("grid")
const searchInput = useTemplateRef<{ focus: () => void }>("search")
const drawerRefresh = ref(0)

const openItemId = computed<number | null>(() => {
  const n = Number(route.query.item)
  return Number.isFinite(n) && n > 0 ? n : null
})

const live = useJobLive(jobId, {
  onItems: (items) => {
    grid.value?.applyUpdates(items)
    if (openItemId.value !== null && items.some((i) => i.id === openItemId.value)) drawerRefresh.value += 1
  },
  onReconnected: () => void grid.value?.refresh(),
})

const job = live.job
const tracks = live.tracks
// 暂停、继续、取消：页头和进度立刻改变（06 第 7.2 节），接口返回前单任务流里的旧状态不会把它改回去
const actions = useJobActions(
  (next) => {
    if (job.value && next.id === job.value.id) live.patchLocal(next)
  },
  { hold: live.hold, release: live.release },
)

// 全局事件流先于单任务流到达时，同步状态
watch(
  () => (jobId.value !== null ? jobsStore.byId(jobId.value) : null),
  (summary) => {
    if (summary && job.value && summary.updated_at > job.value.updated_at) live.patchLocal(summary)
  },
)

const notFound = computed(() => live.error.value instanceof ApiError && live.error.value.status === 404)

// ---- 筛选 ----
const statusBucket = ref<StatusBucket>("all")
const reviewBucket = ref<ReviewBucket>("all")
const labels = ref<string[]>(typeof route.query.label === "string" && route.query.label ? [route.query.label] : [])
const q = ref("")
const debouncedQ = ref("")
const order = ref<ItemOrder>("seq")
let qTimer: number | undefined

watch(q, (value) => {
  window.clearTimeout(qTimer)
  qTimer = window.setTimeout(() => {
    debouncedQ.value = value
  }, 250)
})

const filters = computed<ItemFilters>(() => ({
  status: STATUS_FILTER[statusBucket.value],
  label: labels.value,
  q: debouncedQ.value,
  ...REVIEW_FILTER[reviewBucket.value],
}))

const hasFilters = computed(
  () =>
    statusBucket.value !== "all" || reviewBucket.value !== "all" || labels.value.length > 0 || debouncedQ.value.trim() !== "",
)

function clearFilters(): boolean {
  if (!hasFilters.value) return false
  statusBucket.value = "all"
  reviewBucket.value = "all"
  labels.value = []
  q.value = ""
  debouncedQ.value = ""
  return true
}

const statusOptions = computed<SegmentOption[]>(() => {
  const p = job.value?.progress
  if (!p) return [{ value: "all", label: "全部" }]
  const options: SegmentOption[] = [
    { value: "all", label: "全部", count: formatNumber(p.total) },
    { value: "succeeded", label: "成功", count: formatNumber(p.succeeded) },
    { value: "failed", label: "失败", count: formatNumber(p.failed) },
  ]
  if (p.skipped > 0) options.push({ value: "skipped", label: "跳过", count: formatNumber(p.skipped) })
  if (p.pending + p.running > 0) options.push({ value: "pending", label: "未处理", count: formatNumber(p.pending + p.running) })
  return options
})

const statusModel = computed({
  get: () => statusBucket.value as string,
  set: (value: string) => {
    statusBucket.value = value as StatusBucket
  },
})

const reviewModel = computed<string | undefined>({
  get: () => reviewBucket.value,
  set: (value) => {
    if (value) reviewBucket.value = value as ReviewBucket
  },
})

// ---- 类别与颜色 ----
const categories = computed(() => job.value?.categories ?? [])
const colorMap = computed(() => new Map(categories.value.map((c) => [c.label, c.color_index])))

function colorOf(label: string): number {
  return colorMap.value.get(label) ?? -1
}

function toggleLabels(list: string[], additive: boolean) {
  const current = new Set(labels.value)
  const allSelected = list.every((l) => current.has(l))
  if (additive) {
    for (const l of list) {
      if (allSelected) current.delete(l)
      else current.add(l)
    }
    labels.value = Array.from(current)
  } else {
    labels.value = allSelected && current.size === list.length ? [] : [...list]
  }
}

function removeLabel(label: string) {
  labels.value = labels.value.filter((l) => l !== label)
}

function showFailed() {
  labels.value = []
  statusBucket.value = "failed"
}

async function loadSamples(label: string): Promise<string[]> {
  if (jobId.value === null) return []
  const page = await itemsApi.list(jobId.value, { label: [label], status: ["succeeded"] }, "seq", 0, 3)
  return page.items.map((i) => i.input_preview)
}

// ---- 布局 ----
const status = computed(() => job.value?.status ?? "queued")
const isClassify = computed(() => job.value?.task_type === "classify")
const isRunning = computed(() => status.value === "running" || status.value === "queued")
const showTracks = computed(() => isRunning.value || status.value === "paused")

const trackRows = computed(() => Math.max(1, job.value?.concurrency ?? 1))
const trackRowHeight = computed(() => (trackRows.value <= 8 ? 40 : trackRows.value <= 14 ? 32 : 26))
const liveHeight = computed(() => Math.max(260, trackRows.value * trackRowHeight.value + 40))
const mapLines = computed(() => Math.min(12, categories.value.length) + ((job.value?.progress.failed ?? 0) > 0 ? 1 : 0))
const mapHeight = computed(() => {
  // 运行中与轨道面板等高；意图多时取线网图需要的高度（行距最小 34 px，这里按 40 px 留余量）
  if (showTracks.value) return Math.max(liveHeight.value, 56 + Math.max(1, mapLines.value) * 40)
  return 56 + Math.max(1, mapLines.value) * 52
})

// ---- 页头 ----
const editingName = ref(false)
const nameDraft = ref("")
const nameInput = useTemplateRef<{ focus: () => void; select: () => void }>("nameInput")

async function startRename() {
  if (!job.value) return
  nameDraft.value = job.value.name
  editingName.value = true
  await nextTick()
  nameInput.value?.focus()
  nameInput.value?.select()
}

async function saveName() {
  const j = job.value
  const name = nameDraft.value.trim()
  editingName.value = false
  if (!j || !name || name === j.name) return
  const before = j.name
  live.patchLocal({ name })
  try {
    const next = await jobsApi.update(j.id, { name })
    live.patchLocal(next)
    jobsStore.upsert(next)
  } catch (e) {
    live.patchLocal({ name: before })
    notifyError(e)
  }
}

function cancelRename() {
  editingName.value = false
}

// 暂停原因码不是 user_pause 时，页头下方出现提示条；操作与任务中心相同（06 第 6.3、6.4 节）
const notice = computed(() => (job.value ? pauseNotice(job.value) : null))

async function openLogs() {
  try {
    await systemApi.openFolder("logs")
  } catch (e) {
    notifyError(e)
  }
}

function goFixModel() {
  const id = job.value?.model_id
  void router.push(id ? { path: "/models", query: { edit: String(id) } } : "/models")
}

function togglePause() {
  const j = job.value
  if (!j) return
  if (j.status === "running" || j.status === "queued") void actions.pause(j)
  else if (j.status === "paused") void actions.resume(j)
}

const exportItems = computed<MenuItem[]>(() => {
  const id = jobId.value
  if (id === null) return []
  return [
    { heading: true, label: "Excel" },
    { label: "全部条目", onSelect: () => void actions.exportFile(id, "xlsx", "all") },
    { label: "当前筛选结果", disabled: !hasFilters.value, onSelect: () => void actions.exportFile(id, "xlsx", "filtered", filters.value) },
    { separator: true, label: "" },
    { heading: true, label: "CSV" },
    { label: "全部条目", onSelect: () => void actions.exportFile(id, "csv", "all") },
    { label: "当前筛选结果", disabled: !hasFilters.value, onSelect: () => void actions.exportFile(id, "csv", "filtered", filters.value) },
  ]
})

// 删除（已取消的任务）：有结果（成功条数大于 0）时先确认，确认后立即删除；没有结果的走撤销
const confirmOpen = ref(false)

function askDelete() {
  const j = job.value
  if (!j) return
  if (hasResults(j)) {
    confirmOpen.value = true
    return
  }
  // 没有结果：立刻回到任务中心，toast 里可以撤销，6 秒后才真正删除
  void actions.remove(j, false)
  void router.push("/jobs")
}

async function confirmDelete() {
  confirmOpen.value = false
  const j = job.value
  if (!j) return
  await actions.remove(j, true)
  void router.push("/jobs")
}

// ---- 条目抽屉与对照阅读 ----
function openItem(item: { id: number }) {
  if (!job.value) return
  if (job.value.task_type === "summarize") {
    void router.push(`/jobs/${job.value.id}/read/${item.id}`)
    return
  }
  void router.replace({ query: { ...route.query, item: String(item.id) } })
}

function closeDrawer() {
  const query = { ...route.query }
  delete query.item
  void router.replace({ query })
  void nextTick(() => grid.value?.focusGrid())
}

async function navigate(delta: number) {
  const id = openItemId.value
  if (id === null || !grid.value) return
  const next = await grid.value.getNeighbor(id, delta)
  if (next) void router.replace({ query: { ...route.query, item: String(next.id) } })
}

function openReading(itemId: number) {
  if (job.value) void router.push(`/jobs/${job.value.id}/read/${itemId}`)
}

// ---- 人工复核（06 第 6.4–6.6 节）：E 修正意图或修改摘要，空格切换已复核 ----
const drawer = useTemplateRef<InstanceType<typeof ItemDrawer>>("drawer")

function editItem(item: ItemSummary) {
  const j = job.value
  if (!j) return
  if (item.status !== "succeeded") {
    notify("只有处理成功的条目可以人工修正")
    return
  }
  if (j.task_type === "summarize") {
    void router.push({ path: `/jobs/${j.id}/read/${item.id}`, query: { edit: "1" } })
    return
  }
  openItem(item)
  drawer.value?.startEdit()
}

async function toggleReviewed(item: ItemSummary) {
  const j = job.value
  if (!j) return
  const reviewed = !item.reviewed
  grid.value?.applyUpdates([{ ...item, reviewed }])
  try {
    const saved = await itemsApi.update(j.id, item.id, { reviewed })
    grid.value?.applyUpdates([saved])
    if (openItemId.value === item.id) drawerRefresh.value += 1
  } catch (e) {
    grid.value?.applyUpdates([item])
    notifyError(e)
  }
}

function onItemUpdated(item: ItemSummary) {
  grid.value?.applyUpdates([item])
}

watch(openItemId, (id) => {
  if (id !== null) grid.value?.selectId(id)
})

// ---- 快捷键 ----
useShortcut("p", togglePause, { when: () => openItemId.value === null })
useShortcut("/", () => searchInput.value?.focus())

onMounted(() => {
  ui.clearFilterHandler = clearFilters
})

onBeforeUnmount(() => {
  if (ui.clearFilterHandler === clearFilters) ui.clearFilterHandler = null
  window.clearTimeout(qTimer)
})

function compressionRatio(j: Job): number | null {
  return j.compression?.ratio ?? null
}
</script>

<template>
  <div class="ws-detail">
    <EmptyState v-if="notFound" title="任务不存在或已被删除" description="回到任务中心看看其他任务。">
      <Button variant="primary" @click="router.push('/jobs')">返回任务中心</Button>
    </EmptyState>

    <div v-else-if="!job" class="ws-detail__skeleton">
      <Skeleton height="28px" width="40%" />
      <Skeleton height="16px" width="60%" />
      <Skeleton height="64px" />
      <Skeleton height="280px" />
    </div>

    <template v-else>
      <!-- 页头 -->
      <header class="ws-detail__head">
        <div class="ws-detail__title-block">
          <div v-if="editingName" class="ws-detail__rename">
            <Input
              ref="nameInput"
              v-model="nameDraft"
              :maxlength="100"
              aria-label="任务名称"
              @enter="saveName"
              @escape="cancelRename"
              @blur="saveName"
            />
          </div>
          <h2 v-else class="ws-detail__name">
            <button type="button" class="ws-detail__name-btn" title="点击改名" @click="startRename">{{ job.name }}</button>
          </h2>
          <p class="ws-detail__meta">
            <span>{{ TASK_TYPE_LABEL[job.task_type] }}</span>
            <span>{{ job.file_name }}</span>
            <span>{{ job.model_name }}</span>
            <span>{{ job.prompt_name }} v{{ job.prompt_version }}</span>
            <span>并发 {{ job.concurrency }}</span>
          </p>
        </div>
        <div class="ws-detail__actions">
          <template v-if="job.status === 'running' || job.status === 'queued'">
            <Button variant="secondary" @click="actions.pause(job)">
              <template #icon><Pause :size="16" :stroke-width="1.75" /></template>暂停
            </Button>
            <Button variant="secondary" @click="actions.cancel(job)">
              <template #icon><Square :size="15" :stroke-width="1.75" /></template>取消任务
            </Button>
          </template>
          <template v-else-if="job.status === 'paused'">
            <Button variant="primary" @click="actions.resume(job)">
              <template #icon><Play :size="16" :stroke-width="1.75" /></template>继续
            </Button>
            <Button v-if="job.progress.failed > 0" variant="secondary" @click="actions.retryFailed(job)">
              <template #icon><RotateCcw :size="15" :stroke-width="1.75" /></template>重试失败项
            </Button>
            <Button variant="secondary" @click="actions.cancel(job)">
              <template #icon><Square :size="15" :stroke-width="1.75" /></template>取消任务
            </Button>
          </template>
          <template v-else>
            <Button v-if="job.status === 'completed' && job.progress.failed > 0" variant="secondary" @click="actions.retryFailed(job)">
              <template #icon><RotateCcw :size="15" :stroke-width="1.75" /></template>重试失败项 ({{ formatNumber(job.progress.failed) }})
            </Button>
            <DropdownMenu :items="exportItems">
              <template #trigger>
                <Button variant="primary" data-testid="export-menu">
                  <template #icon><Download :size="16" :stroke-width="1.75" /></template>导出
                </Button>
              </template>
            </DropdownMenu>
            <Button v-if="job.status === 'cancelled'" variant="secondary" @click="askDelete">
              <template #icon><Trash2 :size="15" :stroke-width="1.75" /></template>删除
            </Button>
          </template>
        </div>
      </header>

      <div v-if="notice" class="ws-detail__banner" role="status" data-testid="pause-banner">
        <span>已暂停：{{ notice.text }}</span>
        <span class="ws-detail__banner-actions">
          <Button v-if="notice.fixModel" variant="secondary" size="sm" @click="goFixModel">去修改模型</Button>
          <Button v-if="notice.openLogs" variant="secondary" size="sm" @click="openLogs">打开日志目录</Button>
          <Button variant="primary" size="sm" @click="actions.resume(job)">继续</Button>
        </span>
      </div>

      <LineProgress
        variant="full"
        :progress="job.progress"
        :status="job.status"
        :started-at="job.started_at"
        :finished-at="job.finished_at"
      />

      <!-- 运行中：并行轨道 + 线网图 / 浓缩计；完成后轨道收起 -->
      <div class="ws-detail__live" :class="{ 'is-done': !showTracks, 'is-summary': !isClassify }">
        <section class="ws-detail__tracks" :aria-hidden="!showTracks">
          <div class="ws-detail__panel">
            <ParallelTracks :tracks="tracks" :concurrency="job.concurrency" :status="job.status" />
          </div>
        </section>
        <section class="ws-detail__map">
          <div class="ws-detail__panel" :style="{ height: isClassify ? `${mapHeight}px` : undefined }">
            <LineMap
              v-if="isClassify"
              :categories="categories"
              :failed="job.progress.failed"
              :running="isRunning"
              :selected="labels"
              :height="mapHeight"
              :load-samples="loadSamples"
              @toggle="toggleLabels"
              @show-failed="showFailed"
            />
            <div v-else class="ws-detail__gauge">
              <CompressionGauge
                v-if="job.compression && job.compression.output_chars > 0"
                :input-chars="job.compression.input_chars"
                :output-chars="job.compression.output_chars"
                :ratio="compressionRatio(job)"
              />
              <p v-else class="ws-detail__muted">第一条摘要完成后，这里会显示原文和摘要的字数对比</p>
              <p v-if="job.compression && job.compression.ratio" class="ws-detail__muted">
                已完成摘要的平均压缩比 <span class="num">{{ formatRatio(job.compression.ratio) }}</span>
              </p>
            </div>
          </div>
        </section>
      </div>

      <!-- 结果表工具条 -->
      <div class="ws-detail__toolbar">
        <SegmentedControl v-model="statusModel" :options="statusOptions" aria-label="按状态筛选" />
        <Select v-model="reviewModel" :options="REVIEW_OPTIONS" size="sm" width="128px" aria-label="按复核状态筛选" />
        <div v-if="labels.length" class="ws-detail__chips" aria-label="意图筛选">
          <span v-for="label in labels" :key="label" class="ws-detail__chip">
            <LineBadge :label="label" :color-index="colorOf(label)" :tooltip="false" />
            <button type="button" class="ws-detail__chip-x" :aria-label="`移除意图筛选：${label}`" @click="removeLabel(label)">
              <X :size="12" :stroke-width="2" />
            </button>
          </span>
        </div>
        <Input ref="search" v-model="q" class="ws-detail__search" placeholder="搜索原文、类别、依据或摘要" aria-label="搜索结果">
          <template #prefix><Search :size="16" :stroke-width="1.75" aria-hidden="true" /></template>
        </Input>
        <DropdownMenu v-if="job.status === 'running' || job.status === 'paused' || job.status === 'queued'" :items="exportItems">
          <template #trigger>
            <Button variant="secondary">
              <template #icon><Download :size="16" :stroke-width="1.75" /></template>导出
            </Button>
          </template>
        </DropdownMenu>
      </div>

      <DataGrid
        ref="grid"
        v-model:order="order"
        :job-id="job.id"
        :task-type="job.task_type"
        :filters="filters"
        :color-of="colorOf"
        :click-to-open="job.task_type === 'summarize'"
        :has-filters="hasFilters"
        @open="openItem"
        @edit="editItem"
        @toggle-reviewed="toggleReviewed"
        @clear-filters="clearFilters"
      />

      <ItemDrawer
        ref="drawer"
        :job-id="job.id"
        :item-id="openItemId"
        :task-type="job.task_type"
        :color-of="colorOf"
        :label-options="job.label_options"
        :refresh-key="drawerRefresh"
        @close="closeDrawer"
        @navigate="navigate"
        @read="openReading"
        @updated="onItemUpdated"
      />

      <Dialog v-model:open="confirmOpen" title="删除任务">
        “{{ job.name }}”的 {{ formatNumber(job.progress.succeeded) }} 条结果会一起删除，无法恢复。
        <template #actions>
          <Button variant="secondary" @click="confirmOpen = false">取消</Button>
          <Button variant="danger" @click="confirmDelete">删除任务</Button>
        </template>
      </Dialog>
    </template>
  </div>
</template>

<style scoped>
.ws-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding-top: var(--space-2);
}

.ws-detail__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-6);
}

.ws-detail__title-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.ws-detail__name {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: 700;
  line-height: 1.4;
}

.ws-detail__name-btn {
  max-width: 100%;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--ink);
  font: inherit;
  text-align: left;
  cursor: text;
}

.ws-detail__name-btn:hover {
  text-decoration: underline dashed var(--border-strong);
  text-underline-offset: 6px;
}

.ws-detail__rename {
  width: 480px;
}

.ws-detail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-5);
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-detail__actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--space-2);
}

.ws-detail__banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--status-warn) 12%, transparent);
  color: var(--status-warn);
}

.ws-detail__banner-actions {
  display: flex;
  gap: var(--space-2);
}

.ws-detail__live {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr);
  gap: var(--space-5);
  transition:
    grid-template-columns var(--dur-slow) var(--ease-move),
    gap var(--dur-slow) var(--ease-move);
}

.ws-detail__live.is-done {
  grid-template-columns: minmax(0, 0fr) minmax(0, 1fr);
  gap: 0;
}

.ws-detail__tracks {
  min-width: 0;
  overflow: hidden;
  transition: opacity var(--dur-slow) var(--ease-move);
}

.ws-detail__live.is-done .ws-detail__tracks {
  opacity: 0;
  visibility: hidden;
}

.ws-detail__panel {
  height: 100%;
  min-height: 200px;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
  box-sizing: border-box;
}

.ws-detail__map .ws-detail__panel {
  padding: var(--space-2) var(--space-4);
}

.ws-detail__gauge {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--space-4);
  height: 100%;
  padding: var(--space-4);
}

.ws-detail__muted {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-detail__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ws-detail__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ws-detail__chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.ws-detail__chip-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--ink-2);
}

.ws-detail__chip-x:hover {
  background: var(--surface-2);
  color: var(--ink);
}

.ws-detail__search {
  width: 280px;
  margin-left: auto;
}

@media (prefers-reduced-motion: reduce) {
  .ws-detail__live,
  .ws-detail__tracks {
    transition-duration: 0ms;
  }
}
</style>
