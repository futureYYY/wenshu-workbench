<script setup lang="ts">
// 模型接入（06 第 6.8 节）：像站台的信息牌——一张清楚的列表，不用卡片墙。
// ?edit=3 打开编辑抽屉，?new=1 打开新建抽屉。
import { CircleCheck, CircleX, Ellipsis } from "@lucide/vue"
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { modelsApi } from "@/api/endpoints"
import type { ModelConfig, TaskType } from "@/api/types"
import { TASK_TYPE_LABEL } from "@/api/types"
import Button from "@/components/base/Button.vue"
import DropdownMenu from "@/components/base/DropdownMenu.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import IconButton from "@/components/base/IconButton.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import type { MenuItem } from "@/components/base/types"
import { isDemoModel, isPlaceholderModel, modelHost, useModelsStore } from "@/stores/models"
import { useSettingsStore } from "@/stores/settings"
import { useUiStore } from "@/stores/ui"
import { formatDurationMs, formatRelativeDate } from "@/utils/format"
import { notify, notifyError, notifyUndo } from "@/utils/toast"
import ModelForm from "./ModelForm.vue"

const route = useRoute()
const router = useRouter()
const models = useModelsStore()
const settings = useSettingsStore()
const ui = useUiStore()

const formOpen = ref(false)
const editing = ref<ModelConfig | null>(null)
const testingIds = ref(new Set<number>())
const hiddenIds = ref(new Set<number>())

const list = computed(() => models.visible.filter((m) => !hiddenIds.value.has(m.id)))
// 只有演示模型和还没填写的占位条目时，显示“接入模型”的空状态（06 第 6.12 节）
const hasReal = computed(() => models.realModels.some((m) => !hiddenIds.value.has(m.id) && !isPlaceholderModel(m)))

function connect() {
  const placeholder = models.placeholder
  if (placeholder) openEdit(placeholder)
  else openNew()
}

function syncFromQuery() {
  const edit = Number(route.query.edit)
  if (Number.isFinite(edit) && edit > 0) {
    const m = models.byId(edit)
    if (m) {
      editing.value = m
      formOpen.value = true
    }
    return
  }
  if (route.query.new === "1") {
    editing.value = null
    formOpen.value = true
  }
}

onMounted(async () => {
  await Promise.allSettled([models.load(true), settings.load()])
  syncFromQuery()
})

watch(() => [route.query.edit, route.query.new], syncFromQuery)

watch(formOpen, (open) => {
  if (!open && (route.query.edit || route.query.new)) {
    const query = { ...route.query }
    delete query.edit
    delete query.new
    void router.replace({ query })
  }
})

function openNew() {
  editing.value = null
  formOpen.value = true
}

function openEdit(m: ModelConfig) {
  editing.value = m
  formOpen.value = true
}

async function onSaved(model: ModelConfig, created: boolean) {
  const before = models.byId(model.id)
  models.upsert(model)
  const wasDefaultBoth = before ? before.default_for.length === 2 : false
  if (model.default_for.length === 2 && !wasDefaultBoth && model.provider_kind !== "demo") {
    notify("已设为意图识别和文本摘要的默认模型")
  }
  await Promise.allSettled([settings.load(true), models.load(true)])
  if (created) void router.replace({ query: {} })
}

async function test(m: ModelConfig) {
  const next = new Set(testingIds.value)
  next.add(m.id)
  testingIds.value = next
  try {
    const result = await modelsApi.test(m.id)
    models.upsert(await modelsApi.get(m.id))
    notify(result.ok ? `${m.name}：连接正常` : `${m.name}：${result.message}`)
  } catch (e) {
    notifyError(e)
  } finally {
    const done = new Set(testingIds.value)
    done.delete(m.id)
    testingIds.value = done
  }
}

async function setDefault(m: ModelConfig, task: TaskType) {
  try {
    await settings.patch({ default_model_id: task === "classify" ? { classify: m.id } : { summarize: m.id } })
    await models.load(true)
    notify(`已设为${TASK_TYPE_LABEL[task]}的默认模型`)
  } catch (e) {
    notifyError(e)
  }
}

async function toggleEnabled(m: ModelConfig) {
  try {
    const next = await modelsApi.update(m.id, { enabled: !m.enabled })
    models.upsert(next)
    notify(next.enabled ? `已启用“${m.name}”` : `已停用“${m.name}”`)
  } catch (e) {
    notifyError(e)
  }
}

function remove(m: ModelConfig) {
  hiddenIds.value = new Set(hiddenIds.value).add(m.id)
  const unhide = () => {
    const next = new Set(hiddenIds.value)
    next.delete(m.id)
    hiddenIds.value = next
  }
  let release: () => void = () => undefined
  const flush = notifyUndo(
    `已删除模型“${m.name}”`,
    async () => {
      release()
      try {
        await modelsApi.remove(m.id)
        models.remove(m.id)
        unhide()
        await settings.load(true)
      } catch (e) {
        unhide()
        notifyError(e)
      }
    },
    () => {
      release()
      unhide()
    },
  )
  release = ui.addPendingCommit(flush) as () => void
}

function menu(m: ModelConfig): MenuItem[] {
  const items: MenuItem[] = [
    {
      label: "设为意图识别默认",
      disabled: m.default_for.includes("classify") || !m.enabled,
      onSelect: () => void setDefault(m, "classify"),
    },
    {
      label: "设为文本摘要默认",
      disabled: m.default_for.includes("summarize") || !m.enabled,
      onSelect: () => void setDefault(m, "summarize"),
    },
    { label: m.enabled ? "停用" : "启用", onSelect: () => void toggleEnabled(m) },
  ]
  if (!isDemoModel(m)) {
    items.push({ separator: true, label: "" })
    items.push({
      label: m.active_job_count > 0 ? "删除（有任务在用）" : "删除",
      danger: m.active_job_count === 0,
      disabled: m.active_job_count > 0,
      onSelect: () => remove(m),
    })
  }
  return items
}

function defaultLabels(m: ModelConfig): string[] {
  return m.default_for.map((t) => `${TASK_TYPE_LABEL[t]}默认`)
}
</script>

<template>
  <div class="ws-models">
    <div class="ws-models__top">
      <p class="ws-models__intro">接入 OpenAI 兼容接口：云端 API、公司内网网关、本机 Ollama 或 vLLM 都可以。</p>
      <Button variant="primary" data-testid="new-model" @click="openNew">接入模型</Button>
    </div>

    <div v-if="!models.loaded && models.loading" class="ws-models__list">
      <div v-for="i in 3" :key="i" class="ws-models__row"><Skeleton height="20px" width="60%" /></div>
    </div>
    <EmptyState v-else-if="models.error && !models.loaded" tone="danger" title="模型列表没有加载出来" :description="(models.error as Error).message">
      <Button variant="primary" @click="models.load(true)">重新加载</Button>
    </EmptyState>

    <template v-else>
      <ul class="ws-models__list" aria-label="模型列表">
        <li v-for="m in list" :key="m.id" class="ws-models__row" :class="{ 'is-disabled': !m.enabled }">
          <div class="ws-models__name">
            <span class="ws-models__title">{{ m.name }}</span>
            <span v-if="isDemoModel(m)" class="ws-models__tag">演示</span>
            <span v-if="isPlaceholderModel(m)" class="ws-models__tag is-warn">占位，待填写</span>
            <span v-else-if="!m.enabled" class="ws-models__tag">已停用</span>
          </div>
          <span class="ws-models__host">{{ modelHost(m) }}</span>
          <span class="ws-models__model mono">{{ m.model }}</span>
          <div class="ws-models__status">
            <span v-if="isDemoModel(m)" class="ws-models__muted">不消耗额度，结果是模拟的</span>
            <span v-for="label in defaultLabels(m)" :key="label" class="ws-models__default">{{ label }}</span>
            <span v-if="testingIds.has(m.id)" class="ws-models__testing">
              测试中<span class="ws-models__shuttle" aria-hidden="true"><span class="ws-shuttle" /></span>
            </span>
            <span v-else-if="m.last_test" class="ws-models__test" :class="m.last_test.ok ? 'is-ok' : 'is-fail'">
              <CircleCheck v-if="m.last_test.ok" :size="14" :stroke-width="2" aria-hidden="true" />
              <CircleX v-else :size="14" :stroke-width="2" aria-hidden="true" />
              <span>{{ m.last_test.ok ? (m.last_test.latency_ms !== null ? formatDurationMs(m.last_test.latency_ms) : "连接正常") : m.last_test.message }}</span>
              <span class="ws-models__muted">{{ formatRelativeDate(m.last_test.at) }}</span>
            </span>
            <span v-if="isPlaceholderModel(m)" class="ws-models__muted">{{ m.notes || "编辑填写接口地址、API Key 和模型名" }}</span>
          </div>
          <div class="ws-models__actions">
            <Button variant="secondary" size="sm" :disabled="testingIds.has(m.id) || isPlaceholderModel(m)" @click="test(m)">测试</Button>
            <Button variant="secondary" size="sm" @click="openEdit(m)">编辑</Button>
            <DropdownMenu :items="menu(m)">
              <template #trigger>
                <IconButton :label="`“${m.name}”的更多操作`" size="sm"><Ellipsis :size="16" :stroke-width="1.75" /></IconButton>
              </template>
            </DropdownMenu>
          </div>
        </li>
      </ul>

      <EmptyState v-if="!hasReal" title="接入一个 OpenAI 兼容接口，就能处理真实数据">
        <Button variant="primary" @click="connect">接入模型</Button>
      </EmptyState>
    </template>

    <ModelForm v-model:open="formOpen" :model="editing" @saved="onSaved" />
  </div>
</template>

<style scoped>
.ws-models {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: 1280px;
}

.ws-models__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.ws-models__intro {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-models__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
  overflow: hidden;
}

.ws-models__row {
  display: grid;
  grid-template-columns: minmax(160px, 1.2fr) minmax(140px, 1fr) minmax(140px, 1fr) minmax(220px, 1.6fr) auto;
  align-items: center;
  gap: var(--space-4);
  min-height: 64px;
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--border);
}

.ws-models__row:last-child {
  border-bottom: 0;
}

.ws-models__row.is-disabled .ws-models__title,
.ws-models__row.is-disabled .ws-models__model {
  color: var(--ink-3);
}

.ws-models__name {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.ws-models__title {
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-models__tag {
  flex-shrink: 0;
  padding: 0 8px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  color: var(--ink-2);
  font-size: 11px;
  line-height: 18px;
}

.ws-models__tag.is-warn {
  border-color: var(--status-warn);
  color: var(--status-warn);
}

.ws-models__host {
  overflow: hidden;
  color: var(--ink-2);
  font-size: var(--text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-models__model {
  overflow: hidden;
  font-size: var(--text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-models__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1) var(--space-3);
  min-width: 0;
}

.ws-models__default {
  padding: 0 8px;
  border-radius: var(--radius-pill);
  background: var(--ink);
  color: var(--on-ink);
  font-size: 11px;
  line-height: 20px;
}

.ws-models__test {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-sm);
}

.ws-models__test.is-ok {
  color: var(--status-ok);
}

.ws-models__test.is-fail {
  color: var(--status-danger);
}

.ws-models__muted {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-models__testing {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-models__shuttle {
  position: relative;
  display: inline-block;
  width: 60px;
  height: 2px;
  overflow: hidden;
  background: var(--surface-3);
}

.ws-models__shuttle > span {
  display: block;
  width: 40%;
  height: 100%;
  background: var(--ink);
  animation: ws-shuttle 1.1s var(--ease-move) infinite alternate;
}

.ws-models__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
</style>
