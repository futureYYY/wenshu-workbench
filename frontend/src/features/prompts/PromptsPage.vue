<script setup lang="ts">
// 提示词工坊（06 第 6.7 节）：左栏模板列表，中栏编辑，右栏试运行（可收起）。
// 草稿每次修改 500 ms 后存入 localStorage；离开有未保存修改的页面时确认“保存修改 / 不保存 / 取消”。
import { ChevronDown, PanelRightOpen } from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, useTemplateRef, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter, type RouteLocationNormalized } from "vue-router"
import { ApiError, promptsApi } from "@/api/endpoints"
import type { PromptTemplate, PromptVariable, TaskType } from "@/api/types"
import { TASK_TYPE_LABEL } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Collapsible from "@/components/base/Collapsible.vue"
import Dialog from "@/components/base/Dialog.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import FieldRow from "@/components/base/FieldRow.vue"
import IconButton from "@/components/base/IconButton.vue"
import Input from "@/components/base/Input.vue"
import Kbd from "@/components/base/Kbd.vue"
import NumberInput from "@/components/base/NumberInput.vue"
import Popover from "@/components/base/Popover.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import PromptEditor from "@/components/editor/PromptEditor.vue"
import { draftKey, useDraft } from "@/composables/useDraft"
import { useShortcut } from "@/composables/useShortcuts"
import { usePromptsStore } from "@/stores/prompts"
import { useSettingsStore } from "@/stores/settings"
import { useUiStore } from "@/stores/ui"
import { notify, notifyError, notifyUndo } from "@/utils/toast"
import HistoryDrawer from "./HistoryDrawer.vue"
import PlaygroundPanel from "./PlaygroundPanel.vue"
import PromptList from "./PromptList.vue"
import { formFrom, outputSummary, paramsSummary, sameForm, toDraft, toInput, type PromptForm } from "./promptForm"

const route = useRoute()
const router = useRouter()
const prompts = usePromptsStore()
const settings = useSettingsStore()
const ui = useUiStore()

const playground = useTemplateRef<InstanceType<typeof PlaygroundPanel>>("playground")

const promptId = computed<number | null>(() => {
  const raw = route.params.id
  const n = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(n) && n > 0 ? n : null
})

const template = shallowRef<PromptTemplate | null>(null)
const saved = ref<PromptForm | null>(null)
const form = ref<PromptForm | null>(null)
const loading = ref(false)
const loadError = ref<unknown>(null)
const variables = ref<PromptVariable[]>([])
const saving = ref(false)
const saveError = ref<string | null>(null)
const versionNote = ref("")
const playOpen = ref(true)
const historyOpen = ref(false)
const chunkOpen = ref(false)
const outputOpen = ref(false)
const paramsOpen = ref(false)
const draftAvailable = ref<PromptForm | null>(null)

const taskType = computed<TaskType>(() => template.value?.task_type ?? "classify")
const dirty = computed(() => !!form.value && !!saved.value && !sameForm(form.value, saved.value, taskType.value))
const draftPayload = computed(() => (form.value ? toDraft(form.value, taskType.value) : null))

const draft = useDraft<PromptForm>(() => (promptId.value !== null ? draftKey(promptId.value) : null))

async function load(id: number) {
  loading.value = true
  loadError.value = null
  draftAvailable.value = null
  saveError.value = null
  try {
    const t = await promptsApi.get(id)
    if (promptId.value !== id) return
    template.value = t
    saved.value = formFrom(t)
    form.value = formFrom(t)
    versionNote.value = ""
    const stored = draft.read()
    if (stored && !sameForm(stored, saved.value, t.task_type)) draftAvailable.value = stored
    else if (stored) draft.clear()
    variables.value = await prompts.loadVariables(t.task_type)
  } catch (e) {
    loadError.value = e
  } finally {
    loading.value = false
  }
}

watch(
  promptId,
  async (id) => {
    if (id !== null) {
      await load(id)
      return
    }
    // 不带 id 时进入意图识别的默认模板
    await prompts.load().catch(() => undefined)
    const fallback = prompts.defaultFor("classify")
    if (fallback) void router.replace(`/prompts/${fallback.id}`)
  },
  { immediate: true },
)

// 草稿：每次修改 500 ms 后存入 localStorage
watch(
  form,
  (value) => {
    if (!value || !saved.value) return
    if (sameForm(value, saved.value, taskType.value)) draft.clear()
    else draft.schedule(value)
  },
  { deep: true },
)

function restoreDraft() {
  if (draftAvailable.value) form.value = { ...draftAvailable.value }
  draftAvailable.value = null
}

function discardDraft() {
  draftAvailable.value = null
  draft.clear()
}

// ---- 保存 ----
async function save(): Promise<boolean> {
  const t = template.value
  if (!t || !form.value || saving.value) return false
  saving.value = true
  saveError.value = null
  try {
    const next = await promptsApi.save(t.id, toInput(form.value, t.task_type, versionNote.value))
    const bumped = next.version !== t.version
    template.value = next
    saved.value = formFrom(next)
    form.value = formFrom(next)
    versionNote.value = ""
    draft.clear()
    prompts.upsert(next)
    notify(bumped ? `已保存为 v${next.version}` : "已保存")
    return true
  } catch (e) {
    saveError.value = e instanceof ApiError ? e.message : "保存没有完成，请重试"
    notifyError(e)
    return false
  } finally {
    saving.value = false
  }
}

async function resetBuiltin() {
  const t = template.value
  if (!t) return
  try {
    const next = await promptsApi.resetBuiltin(t.id)
    template.value = next
    saved.value = formFrom(next)
    form.value = formFrom(next)
    draft.clear()
    prompts.upsert(next)
    notify(`已恢复内置默认（新版本 v${next.version}）`)
  } catch (e) {
    notifyError(e)
  }
}

function onRestored(next: PromptTemplate) {
  template.value = next
  saved.value = formFrom(next)
  form.value = formFrom(next)
  draft.clear()
  prompts.upsert(next)
}

// ---- 左栏操作 ----
async function setDefault(p: PromptTemplate) {
  try {
    await settings.patch({
      default_prompt_id: p.task_type === "classify" ? { classify: p.id } : { summarize: p.id },
    })
    prompts.markDefault(p.task_type, p.id)
    notify(`已设为${TASK_TYPE_LABEL[p.task_type]}的默认提示词`)
  } catch (e) {
    notifyError(e)
  }
}

async function copy(p: PromptTemplate) {
  try {
    const next = await promptsApi.create({ copy_from_id: p.id })
    prompts.upsert(next)
    notify(`已复制为“${next.name}”`)
    void router.push(`/prompts/${next.id}`)
  } catch (e) {
    notifyError(e)
  }
}

function uniqueName(task: TaskType, base: string): string {
  const names = new Set(prompts.byType(task).map((p) => p.name))
  if (!names.has(base)) return base
  for (let i = 2; i < 100; i++) if (!names.has(`${base} ${i}`)) return `${base} ${i}`
  return `${base} ${Date.now()}`
}

async function create(task: TaskType) {
  const source = prompts.byType(task).find((p) => p.is_builtin) ?? prompts.defaultFor(task)
  if (!source) return
  try {
    const next = await promptsApi.create({ copy_from_id: source.id, name: uniqueName(task, `新建${TASK_TYPE_LABEL[task]}提示词`) })
    prompts.upsert(next)
    void router.push(`/prompts/${next.id}`)
  } catch (e) {
    notifyError(e)
  }
}

function remove(p: PromptTemplate) {
  prompts.remove(p.id)
  const leaving = p.id === promptId.value
  if (leaving) {
    // 先离开，避免离开提醒
    saved.value = form.value
    const fallback = prompts.defaultFor(p.task_type)
    if (fallback) void router.push(`/prompts/${fallback.id}`)
  }
  let release: () => void = () => undefined
  const flush = notifyUndo(
    `已删除提示词“${p.name}”`,
    async () => {
      release()
      try {
        await promptsApi.remove(p.id)
        await prompts.load(true)
      } catch (e) {
        prompts.upsert(p)
        notifyError(e)
      }
    },
    () => {
      release()
      prompts.upsert(p)
    },
  )
  release = ui.addPendingCommit(flush) as () => void
}

// ---- 离开提醒 ----
const leaveOpen = ref(false)
let leaveResolve: ((choice: "save" | "discard" | "cancel") => void) | null = null

function askLeave(): Promise<"save" | "discard" | "cancel"> {
  leaveOpen.value = true
  return new Promise((resolve) => {
    leaveResolve = resolve
  })
}

function answerLeave(choice: "save" | "discard" | "cancel") {
  leaveOpen.value = false
  leaveResolve?.(choice)
  leaveResolve = null
}

watch(leaveOpen, (open) => {
  if (!open && leaveResolve) answerLeave("cancel")
})

async function guard(): Promise<boolean> {
  if (!dirty.value) return true
  const choice = await askLeave()
  if (choice === "cancel") return false
  if (choice === "save") return await save()
  draft.clear()
  return true
}

onBeforeRouteLeave(() => guard())
onBeforeRouteUpdate((to: RouteLocationNormalized, from: RouteLocationNormalized) => {
  if (to.params.id === from.params.id) return true
  return guard()
})

function onBeforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ""
}

onMounted(() => {
  window.addEventListener("beforeunload", onBeforeUnload)
  void prompts.load().catch(() => undefined)
})

onBeforeUnmount(() => window.removeEventListener("beforeunload", onBeforeUnload))

// ---- 快捷键 ----
useShortcut("ctrl+s", () => void save(), { allowInInput: true })
useShortcut(
  "ctrl+enter",
  () => {
    playOpen.value = true
    void playground.value?.run()
  },
  { allowInInput: true },
)

const outputModel = computed({
  get: () => form.value?.output_mode ?? "json",
  set: (value: string) => {
    if (form.value) form.value.output_mode = value === "text" ? "text" : "json"
  },
})

const temperatureModel = computed({
  get: () => form.value?.temperature ?? null,
  set: (value: number | null) => {
    if (form.value) form.value.temperature = value === null ? null : Math.min(2, Math.max(0, value))
  },
})

const maxOutputModel = computed({
  get: () => form.value?.max_output_tokens ?? null,
  set: (value: number | null) => {
    if (form.value) form.value.max_output_tokens = value
  },
})
</script>

<template>
  <div class="ws-prompts" :class="{ 'is-play-closed': !playOpen }">
    <PromptList
      class="ws-prompts__list"
      :current-id="promptId"
      @set-default="setDefault"
      @copy="copy"
      @remove="remove"
      @create="create"
    />

    <section class="ws-prompts__main">
      <div v-if="loading && !form" class="ws-prompts__skeleton">
        <Skeleton height="28px" width="50%" />
        <Skeleton height="16px" width="70%" />
        <Skeleton height="180px" />
        <Skeleton height="120px" />
      </div>
      <EmptyState v-else-if="loadError && !form" tone="danger" title="提示词没有加载出来" :description="(loadError as Error).message">
        <Button variant="primary" @click="promptId !== null && load(promptId)">重新加载</Button>
      </EmptyState>

      <template v-else-if="form && template">
        <header class="ws-prompts__head">
          <div class="ws-prompts__names">
            <div class="ws-prompts__name-row">
              <input
                v-model="form.name"
                class="ws-prompts__name"
                maxlength="40"
                aria-label="模板名称"
                spellcheck="false"
              />
              <span v-if="template.is_builtin" class="ws-prompts__tag">内置</span>
              <span class="ws-prompts__version num">v{{ template.version }}</span>
            </div>
            <input
              v-model="form.description"
              class="ws-prompts__desc"
              maxlength="200"
              placeholder="一句话说明这个模板的用途"
              aria-label="模板说明"
            />
          </div>
        </header>

        <div v-if="draftAvailable" class="ws-prompts__draft" role="status">
          <span>有上次未保存的草稿</span>
          <span class="ws-prompts__draft-actions">
            <Button size="sm" variant="primary" @click="restoreDraft">恢复草稿</Button>
            <Button size="sm" variant="text" @click="discardDraft">丢弃</Button>
          </span>
        </div>

        <PromptEditor v-model="form.system_prompt" label="系统提示词" template-slot="system" :variables="variables" />
        <PromptEditor v-model="form.user_template" label="用户消息模板" template-slot="user" :variables="variables" />

        <div class="ws-prompts__sections">
          <Collapsible v-if="taskType === 'summarize'" v-model:open="chunkOpen" title="长文本分段" summary="分段模板、合并模板">
            <div class="ws-prompts__stack">
              <PromptEditor v-model="form.chunk_template" label="分段模板" template-slot="chunk" :variables="variables" />
              <PromptEditor v-model="form.merge_template" label="合并模板" template-slot="merge" :variables="variables" />
            </div>
          </Collapsible>

          <Collapsible v-model:open="outputOpen" title="输出解析" :summary="outputSummary(form, taskType)">
            <div class="ws-prompts__stack">
              <FieldRow label="解析方式">
                <SegmentedControl
                  v-model="outputModel"
                  size="sm"
                  aria-label="输出解析方式"
                  :options="[
                    { value: 'json', label: 'JSON 字段映射' },
                    { value: 'text', label: '纯文本' },
                  ]"
                />
              </FieldRow>
              <template v-if="form.output_mode === 'json'">
                <template v-if="taskType === 'classify'">
                  <FieldRow label="意图字段"><Input v-model="form.classify_map.label" mono size="sm" aria-label="意图字段" /></FieldRow>
                  <FieldRow label="置信度字段"><Input v-model="form.classify_map.confidence" mono size="sm" placeholder="不需要可留空" aria-label="置信度字段" /></FieldRow>
                  <FieldRow label="判断依据字段"><Input v-model="form.classify_map.reason" mono size="sm" placeholder="不需要可留空" aria-label="判断依据字段" /></FieldRow>
                </template>
                <template v-else>
                  <FieldRow label="主旨字段"><Input v-model="form.summarize_map.summary" mono size="sm" aria-label="主旨字段" /></FieldRow>
                  <FieldRow label="要点字段"><Input v-model="form.summarize_map.key_points" mono size="sm" placeholder="不需要可留空" aria-label="要点字段" /></FieldRow>
                </template>
              </template>
              <p v-else class="ws-prompts__muted">
                {{ taskType === "classify" ? "取第一个非空行作为意图，自动去掉“意图：”这类前缀。" : "整段输出作为摘要，没有要点。" }}
              </p>
            </div>
          </Collapsible>

          <Collapsible v-model:open="paramsOpen" title="参数覆盖" :summary="paramsSummary(form)">
            <div class="ws-prompts__stack">
              <FieldRow label="温度" hint="留空表示使用模型配置的温度，范围 0 到 2">
                <NumberInput v-model="temperatureModel" :integer="false" :step="0.1" :min="0" :max="2" :width="120" placeholder="按模型" aria-label="温度" />
              </FieldRow>
              <FieldRow label="最大输出" hint="留空表示使用模型配置的最大输出">
                <NumberInput v-model="maxOutputModel" :min="16" :max="32768" :width="140" unit="tokens" placeholder="按模型" aria-label="最大输出 tokens" />
              </FieldRow>
            </div>
          </Collapsible>
        </div>

        <footer class="ws-prompts__bar">
          <span v-if="saveError" class="ws-prompts__error" role="alert">{{ saveError }}</span>
          <span v-else-if="dirty" class="ws-prompts__dirty"><span class="ws-prompts__dot" aria-hidden="true" />有未保存的修改</span>
          <span class="ws-prompts__spacer" />
          <Button variant="text" size="sm" @click="historyOpen = true">历史</Button>
          <Button v-if="template.is_builtin" variant="text" size="sm" @click="resetBuiltin">恢复内置默认</Button>
          <span class="ws-prompts__save">
            <Button variant="primary" :loading="saving" :disabled="!dirty" data-testid="save-prompt" @click="save">
              保存
              <span class="ws-prompts__keys"><Kbd inverse>Ctrl</Kbd><Kbd inverse>S</Kbd></span>
            </Button>
            <Popover side="top" align="end" :width="300">
              <template #trigger>
                <IconButton label="填写版本说明" size="md"><ChevronDown :size="16" :stroke-width="1.75" /></IconButton>
              </template>
              <Input v-model="versionNote" placeholder="本次修改的说明（可选）" :maxlength="100" show-count aria-label="版本说明" />
            </Popover>
          </span>
        </footer>

        <HistoryDrawer
          v-model:open="historyOpen"
          :prompt-id="template.id"
          :task-type="template.task_type"
          :current-version="template.version"
          :variables="variables"
          @restored="onRestored"
        />
      </template>
    </section>

    <section v-if="playOpen && draftPayload" class="ws-prompts__play">
      <PlaygroundPanel ref="playground" :task-type="taskType" :draft="draftPayload" @collapse="playOpen = false" />
    </section>
    <div v-else-if="!playOpen" class="ws-prompts__play-closed">
      <IconButton label="展开试运行" tooltip-side="left" @click="playOpen = true"><PanelRightOpen :size="18" :stroke-width="1.75" /></IconButton>
    </div>

    <Dialog v-model:open="leaveOpen" title="有未保存的修改">
      离开前要保存对“{{ form?.name }}”的修改吗？不保存的话，这些修改会丢失。
      <template #actions>
        <Button variant="text" @click="answerLeave('cancel')">取消</Button>
        <Button variant="secondary" @click="answerLeave('discard')">不保存</Button>
        <Button variant="primary" @click="answerLeave('save')">保存修改</Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.ws-prompts {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 360px;
  align-items: start;
  gap: var(--space-6);
  padding-top: var(--space-2);
}

.ws-prompts.is-play-closed {
  grid-template-columns: 220px minmax(0, 1fr) 40px;
}

.ws-prompts__list {
  position: sticky;
  top: calc(var(--pagebar-height) + var(--space-2));
}

.ws-prompts__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  min-width: 0;
}

.ws-prompts__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-prompts__names {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ws-prompts__name-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.ws-prompts__name,
.ws-prompts__desc {
  min-width: 0;
  padding: 2px 4px;
  margin-left: -4px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--ink);
  font: inherit;
}

.ws-prompts__name {
  flex: 1;
  font-size: var(--text-xl);
  font-weight: 700;
}

.ws-prompts__desc {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-prompts__desc::placeholder {
  color: var(--ink-2);
}

.ws-prompts__name:hover,
.ws-prompts__desc:hover {
  border-color: var(--border);
}

.ws-prompts__name:focus-visible,
.ws-prompts__desc:focus-visible {
  border-color: var(--border-strong);
  background: var(--surface);
}

.ws-prompts__tag {
  padding: 0 8px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-prompts__version {
  color: var(--ink-2);
  font-size: var(--text-md);
  font-weight: 700;
}

.ws-prompts__draft {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--status-warn) 12%, transparent);
  color: var(--status-warn);
  font-size: var(--text-sm);
}

.ws-prompts__draft-actions {
  display: flex;
  gap: var(--space-2);
}

.ws-prompts__sections {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
}

.ws-prompts__stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-prompts__muted {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

/* 底部保存栏吸底 */
.ws-prompts__bar {
  position: sticky;
  bottom: 0;
  z-index: var(--z-header);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
}

.ws-prompts__dirty {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-prompts__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-pill);
  background: var(--status-warn);
}

.ws-prompts__error {
  color: var(--status-danger);
  font-size: var(--text-sm);
}

.ws-prompts__spacer {
  flex: 1;
}

.ws-prompts__save {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.ws-prompts__keys {
  display: inline-flex;
  gap: 2px;
  margin-left: var(--space-2);
}

.ws-prompts__play {
  position: sticky;
  top: calc(var(--pagebar-height) + var(--space-2));
  max-height: calc(100vh - var(--pagebar-height) - var(--space-8));
  overflow-y: auto;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
}

.ws-prompts__play-closed {
  position: sticky;
  top: calc(var(--pagebar-height) + var(--space-2));
}
</style>
