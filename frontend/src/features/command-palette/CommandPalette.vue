<script setup lang="ts">
// 命令面板（06 第 6.10 节）：Ctrl+K 打开，宽 640 px，居中偏上。
// 分组：操作、任务、提示词、模型；↑↓ 选择，Enter 执行，Esc 关闭；空输入时显示最近使用的 5 项。
import { Search } from "@lucide/vue"
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "reka-ui"
import { computed, nextTick, ref, useId, watch } from "vue"
import { useRouter } from "vue-router"
import { systemApi } from "@/api/endpoints"
import { TASK_TYPE_LABEL } from "@/api/types"
import Kbd from "@/components/base/Kbd.vue"
import { useJobsStore } from "@/stores/jobs"
import { useModelsStore } from "@/stores/models"
import { useNewJobStore } from "@/stores/newJob"
import { usePromptsStore } from "@/stores/prompts"
import { useSettingsStore } from "@/stores/settings"
import { useUiStore } from "@/stores/ui"
import { shortcutKeys } from "@/utils/keyboard"
import { fuzzyScore } from "@/utils/text"
import { notifyError } from "@/utils/toast"

type Group = "操作" | "任务" | "提示词" | "模型" | "最近使用"

interface PaletteItem {
  id: string
  group: Exclude<Group, "最近使用">
  label: string
  hint?: string
  shortcut?: string
  run: () => void | Promise<void>
}

const RECENT_KEY = "wenshu.palette-recent"
const JOB_STATUS_TEXT: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  cancelled: "已取消",
}

const ui = useUiStore()
const router = useRouter()
const jobs = useJobsStore()
const prompts = usePromptsStore()
const models = useModelsStore()
const settings = useSettingsStore()
const newJob = useNewJobStore()

const query = ref("")
const active = ref(0)
const listId = useId()
const inputRef = ref<HTMLInputElement | null>(null)

function readRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    const list = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(list) ? list.filter((x): x is string => typeof x === "string").slice(0, 5) : []
  } catch {
    return []
  }
}

function remember(id: string) {
  const list = [id, ...readRecent().filter((x) => x !== id)].slice(0, 5)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  } catch {
    // 忽略
  }
}

async function toggleTheme() {
  const next = ui.toggleTheme()
  try {
    await settings.patch({ theme: next })
  } catch (e) {
    notifyError(e)
  }
}

const actions = computed<PaletteItem[]>(() => [
  {
    id: "action:new",
    group: "操作",
    label: "新建任务",
    shortcut: "ctrl+n",
    run: () => {
      newJob.reset()
      void router.push("/new")
    },
  },
  {
    id: "action:paste",
    group: "操作",
    label: "粘贴文本开始",
    run: () => {
      newJob.reset()
      void router.push({ path: "/new", query: { paste: "1" } })
    },
  },
  { id: "action:model", group: "操作", label: "接入模型", run: () => void router.push({ path: "/models", query: { new: "1" } }) },
  { id: "action:theme", group: "操作", label: "切换主题", shortcut: "ctrl+shift+l", run: toggleTheme },
  {
    id: "action:data",
    group: "操作",
    label: "打开数据目录",
    run: async () => {
      try {
        await systemApi.openFolder("data")
      } catch (e) {
        notifyError(e)
      }
    },
  },
  {
    id: "action:keys",
    group: "操作",
    label: "查看快捷键",
    shortcut: "?",
    run: () => {
      ui.shortcutsOpen = true
    },
  },
])

const jobItems = computed<PaletteItem[]>(() =>
  jobs.all.map((j) => ({
    id: `job:${j.id}`,
    group: "任务",
    label: j.name,
    hint: JOB_STATUS_TEXT[j.status] ?? "",
    run: () => void router.push(`/jobs/${j.id}`),
  })),
)

const promptItems = computed<PaletteItem[]>(() =>
  prompts.items.map((p) => ({
    id: `prompt:${p.id}`,
    group: "提示词",
    label: p.name,
    hint: `${TASK_TYPE_LABEL[p.task_type]} v${p.version}`,
    run: () => void router.push(`/prompts/${p.id}`),
  })),
)

const modelItems = computed<PaletteItem[]>(() =>
  models.visible.map((m) => ({
    id: `model:${m.id}`,
    group: "模型",
    label: m.name,
    hint: m.model,
    run: () => void router.push({ path: "/models", query: { edit: String(m.id) } }),
  })),
)

const allItems = computed(() => [...actions.value, ...jobItems.value, ...promptItems.value, ...modelItems.value])

interface Section {
  title: Group
  items: PaletteItem[]
}

const sections = computed<Section[]>(() => {
  const q = query.value.trim()
  if (!q) {
    const byId = new Map(allItems.value.map((i) => [i.id, i]))
    const recent = readRecent()
      .map((id) => byId.get(id))
      .filter((i): i is PaletteItem => !!i)
    const out: Section[] = []
    if (recent.length) out.push({ title: "最近使用", items: recent })
    out.push({ title: "操作", items: actions.value })
    return out
  }
  const groups: Exclude<Group, "最近使用">[] = ["操作", "任务", "提示词", "模型"]
  const out: Section[] = []
  for (const g of groups) {
    const scored = allItems.value
      .filter((i) => i.group === g)
      .map((i) => ({ i, s: Math.max(fuzzyScore(q, i.label), i.hint ? fuzzyScore(q, i.hint) - 50 : -1) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 8)
      .map((x) => x.i)
    if (scored.length) out.push({ title: g, items: scored })
  }
  return out
})

const flat = computed(() => sections.value.flatMap((s) => s.items))

watch(query, () => {
  active.value = 0
})

watch(
  () => ui.paletteOpen,
  (open) => {
    if (open) {
      query.value = ""
      active.value = 0
      void nextTick(() => inputRef.value?.focus())
    }
  },
)

function onOpenAutoFocus(event: Event) {
  event.preventDefault()
  inputRef.value?.focus()
}

function optionId(index: number): string {
  return `${listId}-${index}`
}

function indexOf(item: PaletteItem): number {
  return flat.value.indexOf(item)
}

function execute(item: PaletteItem | undefined) {
  if (!item) return
  remember(item.id)
  ui.paletteOpen = false
  void nextTick(() => void item.run())
}

function scrollActive() {
  void nextTick(() => document.getElementById(optionId(active.value))?.scrollIntoView({ block: "nearest" }))
}

function onKeydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === "ArrowDown") {
    event.preventDefault()
    active.value = Math.min(flat.value.length - 1, active.value + 1)
    scrollActive()
  } else if (event.key === "ArrowUp") {
    event.preventDefault()
    active.value = Math.max(0, active.value - 1)
    scrollActive()
  } else if (event.key === "Enter") {
    event.preventDefault()
    execute(flat.value[active.value])
  }
}
</script>

<template>
  <DialogRoot v-model:open="ui.paletteOpen">
    <DialogPortal>
      <DialogOverlay class="ws-palette-overlay ws-overlay" />
      <DialogContent class="ws-palette ws-popover" @open-auto-focus="onOpenAutoFocus">
        <DialogTitle class="sr-only">命令面板</DialogTitle>
        <DialogDescription class="sr-only">搜索任务、提示词，或输入命令；↑↓ 选择，Enter 执行，Esc 关闭</DialogDescription>
        <div class="ws-palette__search">
          <Search :size="18" :stroke-width="1.75" aria-hidden="true" />
          <input
            ref="inputRef"
            v-model="query"
            class="ws-palette__input"
            placeholder="搜索任务、提示词，或输入命令"
            role="combobox"
            aria-expanded="true"
            :aria-controls="listId"
            :aria-activedescendant="flat.length ? optionId(active) : undefined"
            aria-autocomplete="list"
            @keydown="onKeydown"
          />
        </div>
        <div :id="listId" class="ws-palette__list" role="listbox" aria-label="搜索结果">
          <template v-for="section in sections" :key="section.title">
            <div class="ws-palette__group" role="presentation">{{ section.title }}</div>
            <div
              v-for="item in section.items"
              :id="optionId(indexOf(item))"
              :key="`${section.title}-${item.id}`"
              role="option"
              class="ws-palette__item"
              :class="{ 'is-active': indexOf(item) === active }"
              :aria-selected="indexOf(item) === active"
              @mousemove="active = indexOf(item)"
              @click="execute(item)"
            >
              <span class="ws-palette__label">{{ item.label }}</span>
              <span v-if="item.hint" class="ws-palette__hint">{{ item.hint }}</span>
              <span v-if="item.shortcut" class="ws-palette__keys">
                <Kbd v-for="k in shortcutKeys(item.shortcut)" :key="k">{{ k }}</Kbd>
              </span>
            </div>
          </template>
          <p v-if="flat.length === 0" class="ws-palette__empty">没有找到“{{ query }}”相关的任务、提示词或命令</p>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style>
.ws-palette-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-palette);
  background: var(--overlay);
}

.ws-palette {
  position: fixed;
  top: 14vh;
  left: 0;
  right: 0;
  z-index: var(--z-palette);
  display: flex;
  flex-direction: column;
  width: 640px;
  max-width: calc(100vw - 48px);
  max-height: 60vh;
  margin: 0 auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-drawer);
  background: var(--surface);
  box-shadow: var(--float-shadow);
  overflow: hidden;
  outline: none;
}

.ws-palette__search {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 52px;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--border);
  color: var(--ink-3);
}

.ws-palette__input {
  flex: 1;
  height: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ink);
  font-size: var(--text-md);
}

.ws-palette__input::placeholder {
  color: var(--ink-2);
}

.ws-palette__list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.ws-palette__group {
  padding: var(--space-2) var(--space-3) var(--space-1);
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-palette__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 36px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-control);
  cursor: pointer;
}

.ws-palette__item.is-active {
  background: var(--surface-2);
}

.ws-palette__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-palette__hint {
  flex-shrink: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-palette__keys {
  display: inline-flex;
  gap: 2px;
  margin-left: auto;
}

.ws-palette__empty {
  margin: 0;
  padding: var(--space-6);
  color: var(--ink-2);
  text-align: center;
}
</style>
