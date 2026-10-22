<script setup lang="ts">
// 任务中心（06 第 6.3 节）：像车站的时刻表——一张紧凑的表，状态清楚，可以直接操作。
// 实时更新（全局 SSE），新任务出现在顶部；暂停原因码不是 user_pause 时，在该行下方显示原因和对应操作。
import { Download, Pause, Play, Search, Square, Trash2 } from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from "vue"
import { useRouter } from "vue-router"
import { jobsApi, systemApi } from "@/api/endpoints"
import type { JobStatus, JobSummary, TaskType } from "@/api/types"
import { TASK_TYPE_SHORT } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Dialog from "@/components/base/Dialog.vue"
import DropdownMenu from "@/components/base/DropdownMenu.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import IconButton from "@/components/base/IconButton.vue"
import Input from "@/components/base/Input.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Select from "@/components/base/Select.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import StatusChip from "@/components/base/StatusChip.vue"
import LineProgress from "@/components/metro/LineProgress.vue"
import { hasResults, useJobActions } from "@/composables/useJobActions"
import { useShortcut } from "@/composables/useShortcuts"
import { useJobsStore } from "@/stores/jobs"
import { useNewJobStore } from "@/stores/newJob"
import { useUiStore } from "@/stores/ui"
import { formatNumber, formatRelativeDate } from "@/utils/format"
import { pauseNotice } from "@/utils/pauseReason"
import { notifyError } from "@/utils/toast"

type Bucket = "all" | "running" | "paused" | "completed" | "cancelled"

const BUCKET_STATUS: Record<Bucket, JobStatus[]> = {
  all: [],
  running: ["running", "queued"],
  paused: ["paused"],
  completed: ["completed"],
  cancelled: ["cancelled"],
}

const router = useRouter()
const jobsStore = useJobsStore()
const newJob = useNewJobStore()
const ui = useUiStore()
const actions = useJobActions()

const bucket = ref<Bucket>("all")
const taskType = ref<string>("all")
const q = ref("")
const debouncedQ = ref("")
const items = ref<JobSummary[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref<unknown>(null)
const counts = ref<Record<Bucket, number | null>>({ all: null, running: null, paused: null, completed: null, cancelled: null })
const searchRef = useTemplateRef<{ focus: () => void }>("search")

let seq = 0
let qTimer: number | undefined
let countTimer: number | undefined

watch(q, (value) => {
  window.clearTimeout(qTimer)
  qTimer = window.setTimeout(() => {
    debouncedQ.value = value
  }, 250)
})

const filterTask = computed<TaskType | null>(() => (taskType.value === "all" ? null : (taskType.value as TaskType)))
const hasFilters = computed(() => bucket.value !== "all" || taskType.value !== "all" || debouncedQ.value.trim() !== "")

async function load(append = false) {
  const mySeq = ++seq
  loading.value = true
  try {
    const page = await jobsApi.list({
      status: BUCKET_STATUS[bucket.value],
      task_type: filterTask.value,
      q: debouncedQ.value,
      offset: append ? items.value.length : 0,
      limit: 50,
    })
    if (mySeq !== seq) return
    items.value = append ? [...items.value, ...page.items] : page.items
    total.value = page.total
    jobsStore.setMany(page.items)
    loadError.value = null
  } catch (e) {
    if (mySeq === seq) loadError.value = e
  } finally {
    if (mySeq === seq) loading.value = false
  }
}

async function loadCounts() {
  const buckets: Bucket[] = ["all", "running", "paused", "completed", "cancelled"]
  try {
    const results = await Promise.all(
      buckets.map((b) => jobsApi.list({ status: BUCKET_STATUS[b], task_type: filterTask.value, q: debouncedQ.value, limit: 1 })),
    )
    const next = { ...counts.value }
    buckets.forEach((b, i) => {
      next[b] = results[i]?.total ?? null
    })
    counts.value = next
  } catch {
    // 计数失败不影响列表
  }
}

watch([bucket, filterTask, debouncedQ], () => {
  void load()
  void loadCounts()
})

// 全局 SSE：更新列表里已有的行，删除的行移除，新任务出现在顶部
watch(
  () => jobsStore.map,
  (map, old) => {
    const deleted = new Set<number>()
    if (old) for (const id of old.keys()) if (!map.has(id)) deleted.add(id)
    let changed = false
    const next = items.value
      .filter((j) => {
        if (deleted.has(j.id)) {
          changed = true
          return false
        }
        return true
      })
      .map((j) => {
        const fresh = map.get(j.id)
        if (fresh && fresh !== j) {
          changed = true
          return fresh
        }
        return j
      })
    const known = new Set(next.map((j) => j.id))
    const newest = items.value[0]?.created_at ?? ""
    const created = Array.from(map.values()).filter((j) => !known.has(j.id) && matches(j) && j.created_at > newest)
    if (created.length && !loading.value) {
      changed = true
      next.unshift(...created.sort((a, b) => b.created_at.localeCompare(a.created_at)))
      total.value += created.length
    }
    if (changed) items.value = next
    window.clearTimeout(countTimer)
    countTimer = window.setTimeout(() => void loadCounts(), 1000)
  },
)

function matches(job: JobSummary): boolean {
  const statuses = BUCKET_STATUS[bucket.value]
  if (statuses.length && !statuses.includes(job.status)) return false
  if (filterTask.value && job.task_type !== filterTask.value) return false
  const query = debouncedQ.value.trim().toLowerCase()
  if (query && !job.name.toLowerCase().includes(query) && !job.file_name.toLowerCase().includes(query)) return false
  return true
}

const visibleItems = computed(() => items.value.filter((j) => !jobsStore.hidden.has(j.id)))

const bucketOptions = computed(() => [
  { value: "all", label: "全部", count: counts.value.all ?? undefined },
  { value: "running", label: "运行中", count: counts.value.running ?? undefined },
  { value: "paused", label: "已暂停", count: counts.value.paused ?? undefined },
  { value: "completed", label: "已完成", count: counts.value.completed ?? undefined },
  { value: "cancelled", label: "已取消", count: counts.value.cancelled ?? undefined },
])

const bucketModel = computed({
  get: () => bucket.value as string,
  set: (value: string) => {
    bucket.value = value as Bucket
  },
})

const typeOptions = [
  { value: "all", label: "全部类型" },
  { value: "classify", label: "意图识别" },
  { value: "summarize", label: "文本摘要" },
]

const typeModel = computed({
  get: () => taskType.value,
  set: (value: string | undefined) => {
    taskType.value = value ?? "all"
  },
})

function clearFilters(): boolean {
  if (!hasFilters.value) return false
  bucket.value = "all"
  taskType.value = "all"
  q.value = ""
  debouncedQ.value = ""
  return true
}

async function goFixModel(job: JobSummary) {
  try {
    const detail = await jobsApi.get(job.id)
    if (detail.model_id !== null) void router.push({ path: "/models", query: { edit: String(detail.model_id) } })
    else void router.push("/models")
  } catch (e) {
    notifyError(e)
  }
}

async function openLogs() {
  try {
    await systemApi.openFolder("logs")
  } catch (e) {
    notifyError(e)
  }
}

// 删除：有结果（成功条数大于 0）的任务先确认，确认后立即删除；没有结果的走 6 秒撤销（06 第 6.3、7.2 节）
const confirmJob = ref<JobSummary | null>(null)
const confirmOpen = computed({
  get: () => confirmJob.value !== null,
  set: (open: boolean) => {
    if (!open) confirmJob.value = null
  },
})

function askDelete(job: JobSummary) {
  if (hasResults(job)) confirmJob.value = job
  else void actions.remove(job, false, () => removeLocal(job.id))
}

async function confirmDelete() {
  const job = confirmJob.value
  confirmJob.value = null
  if (job) await actions.remove(job, true, () => removeLocal(job.id))
}

function removeLocal(id: number) {
  items.value = items.value.filter((j) => j.id !== id)
  total.value = Math.max(0, total.value - 1)
}

function exportMenu(job: JobSummary) {
  return [
    { label: "导出 Excel", onSelect: () => void actions.exportFile(job.id, "xlsx", "all") },
    { label: "导出 CSV", onSelect: () => void actions.exportFile(job.id, "csv", "all") },
  ]
}

function newTask() {
  newJob.reset()
  void router.push("/new")
}

useShortcut("/", () => searchRef.value?.focus())

onMounted(() => {
  ui.clearFilterHandler = clearFilters
  void load()
  void loadCounts()
})

onBeforeUnmount(() => {
  if (ui.clearFilterHandler === clearFilters) ui.clearFilterHandler = null
  window.clearTimeout(qTimer)
  window.clearTimeout(countTimer)
})
</script>

<template>
  <div class="ws-jobs">
    <div class="ws-jobs__toolbar">
      <SegmentedControl v-model="bucketModel" :options="bucketOptions" aria-label="按状态筛选" />
      <Select v-model="typeModel" :options="typeOptions" aria-label="按任务类型筛选" width="140px" />
      <Input ref="search" v-model="q" class="ws-jobs__search" placeholder="搜索任务名或文件名" aria-label="搜索任务名或文件名">
        <template #prefix><Search :size="16" :stroke-width="1.75" aria-hidden="true" /></template>
      </Input>
    </div>

    <div class="ws-jobs__table" role="table" aria-label="任务列表">
      <div class="ws-jobs__row is-head" role="row">
        <span role="columnheader">状态</span>
        <span role="columnheader">任务</span>
        <span role="columnheader">类型</span>
        <span role="columnheader">进度</span>
        <span role="columnheader">模型</span>
        <span role="columnheader">创建</span>
        <span role="columnheader" class="sr-only">操作</span>
      </div>

      <template v-if="loading && items.length === 0">
        <div v-for="i in 5" :key="i" class="ws-jobs__row" role="row">
          <span v-for="j in 6" :key="j"><Skeleton width="70%" /></span>
          <span />
        </div>
      </template>

      <EmptyState v-else-if="loadError && items.length === 0" tone="danger" title="任务列表没有加载出来" :description="(loadError as Error).message">
        <Button variant="primary" @click="load()">重新加载</Button>
      </EmptyState>

      <EmptyState v-else-if="visibleItems.length === 0 && hasFilters" title="没有符合筛选的任务" description="换一个条件试试。">
        <Button variant="primary" @click="clearFilters">清除筛选</Button>
      </EmptyState>

      <EmptyState v-else-if="visibleItems.length === 0" title="还没有任务。把文件拖进窗口就能开始第一个。">
        <Button variant="primary" @click="newTask">新建任务</Button>
      </EmptyState>

      <template v-else>
      <template v-for="job in visibleItems" :key="job.id">
        <div class="ws-jobs__row is-body" role="row" @click="router.push(`/jobs/${job.id}`)">
          <span role="cell"><StatusChip :status="job.status" /></span>
          <span role="cell" class="ws-jobs__name">
            <RouterLink :to="`/jobs/${job.id}`" @click.stop>{{ job.name }}</RouterLink>
            <span class="ws-jobs__file">{{ job.file_name }}</span>
          </span>
          <span role="cell" class="ws-jobs__muted">{{ TASK_TYPE_SHORT[job.task_type] }}</span>
          <span role="cell"><LineProgress :progress="job.progress" :status="job.status" :width="220" /></span>
          <span role="cell" class="ws-jobs__muted ws-jobs__ellipsis">{{ job.model_name }}</span>
          <span role="cell" class="ws-jobs__muted">{{ formatRelativeDate(job.created_at) }}</span>
          <span role="cell" class="ws-jobs__actions" @click.stop>
            <template v-if="job.status === 'running' || job.status === 'queued'">
              <IconButton label="暂停" size="sm" @click="actions.pause(job)"><Pause :size="16" :stroke-width="1.75" /></IconButton>
              <IconButton label="取消任务" size="sm" @click="actions.cancel(job)"><Square :size="15" :stroke-width="1.75" /></IconButton>
            </template>
            <template v-else-if="job.status === 'paused'">
              <IconButton label="继续" size="sm" @click="actions.resume(job)"><Play :size="16" :stroke-width="1.75" /></IconButton>
              <IconButton label="取消任务" size="sm" @click="actions.cancel(job)"><Square :size="15" :stroke-width="1.75" /></IconButton>
            </template>
            <template v-else>
              <DropdownMenu :items="exportMenu(job)">
                <template #trigger>
                  <IconButton label="导出" size="sm"><Download :size="16" :stroke-width="1.75" /></IconButton>
                </template>
              </DropdownMenu>
              <IconButton label="删除" size="sm" @click="askDelete(job)"><Trash2 :size="16" :stroke-width="1.75" /></IconButton>
            </template>
          </span>
        </div>
        <div v-if="pauseNotice(job)" class="ws-jobs__reason" role="row">
          <span class="ws-jobs__reason-text" role="cell">{{ pauseNotice(job)?.text }}</span>
          <span class="ws-jobs__reason-actions" role="cell">
            <Button v-if="pauseNotice(job)?.fixModel" variant="text" size="sm" @click="goFixModel(job)">去修改模型</Button>
            <Button v-if="pauseNotice(job)?.openLogs" variant="text" size="sm" @click="openLogs">打开日志目录</Button>
            <Button variant="secondary" size="sm" @click="actions.resume(job)">继续</Button>
          </span>
        </div>
      </template>
      </template>
    </div>

    <div v-if="items.length < total" class="ws-jobs__more">
      <Button variant="secondary" :loading="loading" @click="load(true)">
        加载更多（还有 {{ formatNumber(total - items.length) }} 个）
      </Button>
    </div>

    <Dialog v-model:open="confirmOpen" title="删除任务">
      <template v-if="confirmJob">
        “{{ confirmJob.name }}”的 {{ formatNumber(confirmJob.progress.succeeded) }} 条结果会一起删除，无法恢复。
      </template>
      <template #actions>
        <Button variant="secondary" @click="confirmJob = null">取消</Button>
        <Button variant="danger" @click="confirmDelete">删除任务</Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.ws-jobs {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-jobs__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ws-jobs__search {
  width: 280px;
  margin-left: auto;
}

.ws-jobs__table {
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
  overflow: hidden;
}

.ws-jobs__row {
  display: grid;
  grid-template-columns: 96px minmax(220px, 2fr) 56px 280px minmax(120px, 1fr) 96px 88px;
  align-items: center;
  gap: var(--space-3);
  min-height: 52px;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--border);
}

.ws-jobs__row.is-head {
  min-height: 36px;
  color: var(--ink-2);
  font-size: var(--text-xs);
  font-weight: 500;
}

.ws-jobs__row.is-body {
  cursor: pointer;
}

.ws-jobs__row.is-body:hover {
  background: var(--surface-2);
}

.ws-jobs__name {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ws-jobs__name a {
  overflow: hidden;
  color: var(--ink);
  font-weight: 500;
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-jobs__name a:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.ws-jobs__file {
  overflow: hidden;
  color: var(--ink-2);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-jobs__muted {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-jobs__ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 行悬停时右侧出现操作（键盘聚焦时同样出现） */
.ws-jobs__actions {
  display: flex;
  justify-content: flex-end;
  gap: 2px;
  opacity: 0;
  transition: opacity var(--dur-fast) var(--ease-out);
}

.ws-jobs__row:hover .ws-jobs__actions,
.ws-jobs__row:focus-within .ws-jobs__actions {
  opacity: 1;
}

.ws-jobs__reason {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-2) var(--space-4) var(--space-2) calc(96px + var(--space-4) + var(--space-3));
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--status-warn) 8%, transparent);
}

.ws-jobs__reason-text {
  color: var(--status-warn);
  font-size: var(--text-sm);
}

.ws-jobs__reason-actions {
  display: flex;
  gap: var(--space-2);
}

.ws-jobs__more {
  display: flex;
  justify-content: center;
}
</style>
