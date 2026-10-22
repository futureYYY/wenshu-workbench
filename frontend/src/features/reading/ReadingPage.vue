<script setup lang="ts">
// 摘要对照阅读（06 第 5.1 节 ExpressTrace，路由 /jobs/:id/read/:itemId）。
// 顶部：返回结果、行号、上一条下一条、复核、修改摘要、单条浓缩计；J / K 切换上一条、下一条结果。
// 人工复核（06 第 6.5 节）：E 或“修改摘要”在右栏改摘要主旨（要点保持模型输出），Ctrl+Enter 保存、Esc 取消；
// 改过的摘要标“人工修改”，下方可以展开“模型原摘要”，也可以撤销修改。带 ?edit=1 进入时直接开始修改。
import { useEventListener } from "@vueuse/core"
import { ArrowDown, ArrowLeft, ArrowUp, CircleCheck, Pencil } from "@lucide/vue"
import { computed, nextTick, ref, useTemplateRef, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { itemsApi } from "@/api/endpoints"
import type { ItemDetail, ItemSummary } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Collapsible from "@/components/base/Collapsible.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import IconButton from "@/components/base/IconButton.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import Textarea from "@/components/base/Textarea.vue"
import CompressionGauge from "@/components/metro/CompressionGauge.vue"
import ExpressTrace from "@/components/metro/ExpressTrace.vue"
import { useShortcut } from "@/composables/useShortcuts"
import { failureSentence } from "@/utils/errors"
import { renderMarkdown } from "@/utils/markdown"
import { notify, notifyError } from "@/utils/toast"

const route = useRoute()
const router = useRouter()

const jobId = computed(() => Number(route.params.id))
const itemId = computed(() => Number(route.params.itemId))

const item = ref<ItemDetail | null>(null)
const loading = ref(false)
const loadError = ref<unknown>(null)
let seq = 0

// 人工复核的状态（切换条目时在下面的 watch 里复位，所以要先声明）
const editing = ref(false)
const draft = ref("")
const saving = ref(false)
const savingReviewed = ref(false)
const showOriginal = ref(false)
const editor = useTemplateRef<{ focus: () => void }>("editor")

async function load() {
  const mySeq = ++seq
  loading.value = true
  try {
    const detail = await itemsApi.get(jobId.value, itemId.value)
    if (mySeq !== seq) return
    item.value = detail
    loadError.value = null
    if (route.query.edit === "1") {
      void router.replace({ query: {} })
      startEdit()
    }
  } catch (e) {
    if (mySeq === seq) loadError.value = e
  } finally {
    if (mySeq === seq) loading.value = false
  }
}

watch(
  [jobId, itemId],
  () => {
    editing.value = false
    showOriginal.value = false
    void load()
  },
  { immediate: true },
)

/** 按行号顺序找上一条、下一条成功的结果（seq 连续，按位置取一个窗口） */
async function neighbor(delta: number): Promise<ItemSummary | null> {
  const current = item.value
  if (!current) return null
  const size = 20
  let offset = delta > 0 ? current.seq : Math.max(0, current.seq - 1 - size)
  for (let round = 0; round < 10; round++) {
    const page = await itemsApi.list(jobId.value, {}, "seq", offset, size)
    if (page.items.length === 0) return null
    const candidates = page.items.filter((i) => i.status === "succeeded" && (delta > 0 ? i.seq > current.seq : i.seq < current.seq))
    const found = delta > 0 ? candidates[0] : candidates[candidates.length - 1]
    if (found) return found
    if (delta > 0) {
      offset += size
      if (offset >= page.total) return null
    } else {
      if (offset === 0) return null
      offset = Math.max(0, offset - size)
    }
  }
  return null
}

async function go(delta: number) {
  if (blockedByDraft()) return
  const next = await neighbor(delta)
  if (next) void router.replace(`/jobs/${jobId.value}/read/${next.id}`)
  else notify(delta > 0 ? "已经是最后一条结果" : "已经是第一条结果")
}

function back() {
  if (blockedByDraft()) return
  void router.push({ path: `/jobs/${jobId.value}` })
}

// ---- 人工复核：修改摘要、标记已复核 ----
const editable = computed(() => item.value?.status === "succeeded" && !!item.value.summary)
const edited = computed(() => (item.value?.manual_summary ?? null) !== null)
/** 有效摘要：人工修改过的取修改后的 */
const effectiveSummary = computed(() => item.value?.manual_summary ?? item.value?.summary ?? "")
const originalHtml = computed(() => renderMarkdown(item.value?.summary ?? ""))
const dirty = computed(() => editing.value && draft.value.trim() !== effectiveSummary.value.trim())

function blockedByDraft(): boolean {
  if (!dirty.value) return false
  notify("先保存或取消正在修改的摘要")
  return true
}

function startEdit() {
  if (editing.value) return
  if (!editable.value) {
    notify("只有处理成功的条目可以修改摘要")
    return
  }
  draft.value = effectiveSummary.value
  editing.value = true
  void nextTick(() => editor.value?.focus())
}

function cancelEdit() {
  editing.value = false
  draft.value = ""
}

async function saveEdit() {
  const current = item.value
  if (!current || saving.value) return
  const text = draft.value.trim()
  if (!text) {
    notify("摘要不能为空；要恢复模型的摘要，请点“撤销修改”")
    return
  }
  saving.value = true
  try {
    await itemsApi.update(jobId.value, current.id, { manual_summary: text })
    editing.value = false
    await load()
    notify("已保存修改")
  } catch (e) {
    notifyError(e)
  } finally {
    saving.value = false
  }
}

async function revertEdit() {
  const current = item.value
  if (!current || saving.value) return
  saving.value = true
  try {
    await itemsApi.update(jobId.value, current.id, { manual_summary: null })
    editing.value = false
    showOriginal.value = false
    await load()
    notify("已撤销修改")
  } catch (e) {
    notifyError(e)
  } finally {
    saving.value = false
  }
}

async function toggleReviewed() {
  const current = item.value
  if (!current || savingReviewed.value) return
  const reviewed = !current.reviewed
  item.value = { ...current, reviewed }
  savingReviewed.value = true
  try {
    await itemsApi.update(jobId.value, current.id, { reviewed })
  } catch (e) {
    if (item.value?.id === current.id) item.value = { ...item.value, reviewed: current.reviewed }
    notifyError(e)
  } finally {
    savingReviewed.value = false
  }
}

// 有没保存的修改时，关闭窗口前提醒（06 第 7.5 节）
useEventListener(window, "beforeunload", (event: BeforeUnloadEvent) => {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ""
})

useShortcut(["j"], () => void go(1))
useShortcut(["k"], () => void go(-1))
useShortcut("e", () => startEdit(), { when: () => !editing.value })

const segments = computed(() => item.value?.segments ?? (item.value ? [item.value.input_text] : []))
</script>

<template>
  <div class="ws-reading">
    <header class="ws-reading__bar">
      <Button variant="text" size="sm" @click="back">
        <template #icon><ArrowLeft :size="16" :stroke-width="1.75" /></template>
        返回结果
      </Button>
      <span v-if="item" class="ws-reading__row">第 <span class="num">{{ item.row_number }}</span> 行</span>
      <span class="ws-reading__nav">
        <IconButton label="上一条" shortcut="k" @click="go(-1)"><ArrowUp :size="16" :stroke-width="1.75" /></IconButton>
        <IconButton label="下一条" shortcut="j" @click="go(1)"><ArrowDown :size="16" :stroke-width="1.75" /></IconButton>
      </span>
      <span class="ws-reading__spacer" />
      <template v-if="item && editable">
        <Button
          size="sm"
          variant="secondary"
          class="ws-reading__review"
          :class="{ 'is-on': item.reviewed }"
          :aria-pressed="item.reviewed ? 'true' : 'false'"
          data-testid="toggle-reviewed"
          @click="toggleReviewed"
        >
          <template #icon><CircleCheck :size="14" :stroke-width="1.75" /></template>
          {{ item.reviewed ? "已复核" : "标记已复核" }}
        </Button>
        <Button v-if="!editing" size="sm" variant="secondary" data-testid="edit-summary" @click="startEdit">
          <template #icon><Pencil :size="14" :stroke-width="1.75" /></template>
          修改摘要
        </Button>
      </template>
      <CompressionGauge
        v-if="item && item.output_chars"
        :input-chars="item.input_chars"
        :output-chars="item.output_chars"
        :ratio="item.compression_ratio"
        :max-length="200"
      />
    </header>

    <div v-if="loading && !item" class="ws-reading__skeleton">
      <Skeleton height="24px" width="30%" />
      <Skeleton height="360px" />
    </div>
    <EmptyState v-else-if="loadError && !item" tone="danger" title="这一条没有加载出来" :description="(loadError as Error).message">
      <Button variant="primary" @click="load">重新加载</Button>
    </EmptyState>
    <template v-else-if="item">
      <EmptyState
        v-if="item.status !== 'succeeded' || !item.summary"
        :tone="item.status === 'failed' ? 'danger' : 'neutral'"
        :title="item.status === 'failed' ? '这一条处理失败了' : '这一条还没有摘要'"
        :description="item.status === 'failed' ? failureSentence(item.error_code, item.error_message) : '处理完成后可以在这里对照阅读。'"
      >
        <Button variant="secondary" @click="back">返回结果</Button>
      </EmptyState>
      <ExpressTrace
        v-else
        class="ws-reading__trace"
        :segments="segments"
        :summary="effectiveSummary"
        :key-points="item.key_points ?? []"
        :edited="edited"
      >
        <template v-if="editing" #summary>
          <div class="ws-reading__editor">
            <Textarea
              ref="editor"
              v-model="draft"
              :rows="6"
              :maxlength="10000"
              aria-label="修改摘要"
              data-testid="summary-editor"
              @submit="saveEdit"
              @keydown.esc.stop="cancelEdit"
            />
            <p class="ws-reading__hint">要点保持模型的输出。Ctrl+Enter 保存，Esc 取消。</p>
            <div class="ws-reading__editor-actions">
              <Button variant="primary" size="sm" :loading="saving" data-testid="save-summary" @click="saveEdit">保存</Button>
              <Button variant="secondary" size="sm" :disabled="saving" @click="cancelEdit">取消</Button>
            </div>
          </div>
        </template>
        <template v-if="edited && !editing" #after-summary>
          <div class="ws-reading__original">
            <Collapsible v-model:open="showOriginal" title="模型原摘要">
              <div class="ws-reading__original-text" v-html="originalHtml" />
            </Collapsible>
            <Button size="sm" variant="text" :disabled="saving" @click="revertEdit">撤销修改</Button>
          </div>
        </template>
      </ExpressTrace>
    </template>
  </div>
</template>

<style scoped>
.ws-reading {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  height: calc(100vh - var(--pagebar-height) - var(--space-12));
  min-height: 480px;
}

.ws-reading__bar {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.ws-reading__row {
  font-size: var(--text-md);
  font-weight: 500;
}

.ws-reading__nav {
  display: inline-flex;
  gap: 2px;
}

.ws-reading__spacer {
  flex: 1;
}

.ws-reading__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-reading__trace {
  flex: 1;
  min-height: 0;
}

.ws-reading__review.is-on {
  border-color: var(--status-ok);
  color: var(--status-ok);
}

.ws-reading__editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.ws-reading__hint {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-reading__editor-actions {
  display: flex;
  gap: var(--space-2);
}

.ws-reading__original {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.ws-reading__original-text {
  color: var(--ink-2);
  font-size: var(--text-sm);
  line-height: 1.75;
}
</style>
