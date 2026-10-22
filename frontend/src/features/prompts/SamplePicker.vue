<script setup lang="ts">
// 试运行“从文件选”：选一个已上传的文件，点表头选文本列，点一行作为样本。
import { computed, ref, watch } from "vue"
import { filesApi } from "@/api/endpoints"
import type { FilePreview, JoinMode, SampleRow } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Drawer from "@/components/base/Drawer.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Select from "@/components/base/Select.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import type { SelectOption } from "@/components/base/types"
import PreviewGrid from "@/components/data/PreviewGrid.vue"
import { useFilesStore } from "@/stores/files"
import { formatNumber } from "@/utils/format"

const open = defineModel<boolean>("open", { default: false })
const emit = defineEmits<{ pick: [sample: SampleRow, text: string] }>()

const files = useFilesStore()
const fileId = ref<string | undefined>(undefined)
const sheet = ref<string | undefined>(undefined)
const headerRow = ref("1")
const preview = ref<FilePreview | null>(null)
const loading = ref(false)
const loadError = ref<unknown>(null)
const textColumns = ref<string[]>([])
const joinMode = ref<JoinMode>("labeled")
const activeRow = ref<number | null>(null)

watch(open, (value) => {
  if (value) void files.load(true).catch(() => undefined)
})

const file = computed(() => files.recent.find((f) => String(f.id) === fileId.value) ?? null)
const isLines = computed(() => file.value?.kind === "lines")

const fileOptions = computed<SelectOption[]>(() =>
  files.recent.map((f) => ({ value: String(f.id), label: f.original_name, hint: f.ext })),
)
const sheetOptions = computed<SelectOption[]>(() =>
  (file.value?.sheets ?? []).map((s) => ({ value: s.name, label: s.name, hint: `${formatNumber(s.row_count)} 行` })),
)
const headerOptions: SelectOption[] = [
  { value: "0", label: "无表头" },
  ...Array.from({ length: 10 }, (_, i) => ({ value: String(i + 1), label: `第 ${i + 1} 行` })),
]

async function loadPreview() {
  const f = file.value
  if (!f) return
  loading.value = true
  loadError.value = null
  try {
    const result = await filesApi.preview(f.id, {
      sheet: isLines.value ? null : (sheet.value ?? null),
      header_row: isLines.value ? 0 : Number(headerRow.value),
      offset: 0,
      limit: 200,
    })
    preview.value = result
    const keys = new Set(result.columns.map((c) => c.key))
    const kept = textColumns.value.filter((k) => keys.has(k))
    textColumns.value = kept.length ? kept : [...result.suggested_text_columns]
    activeRow.value = null
  } catch (e) {
    loadError.value = e
  } finally {
    loading.value = false
  }
}

watch(fileId, () => {
  const f = file.value
  sheet.value = f?.kind === "table" ? f.sheets[0]?.name : undefined
  headerRow.value = f?.kind === "table" ? "1" : "0"
  textColumns.value = []
  preview.value = null
  void loadPreview()
})

watch([sheet, headerRow], () => {
  if (file.value) void loadPreview()
})

function toggle(key: string) {
  textColumns.value = textColumns.value.includes(key) ? textColumns.value.filter((k) => k !== key) : [...textColumns.value, key]
}

const joinModel = computed({
  get: () => joinMode.value as string,
  set: (value: string) => {
    joinMode.value = value === "plain" ? "plain" : "labeled"
  },
})

const sampleText = computed(() => {
  const p = preview.value
  if (!p || activeRow.value === null) return ""
  const row = p.rows.find((r) => r.row_number === activeRow.value)
  if (!row) return ""
  const titles = new Map(p.columns.map((c) => [c.key, c.title]))
  const parts: string[] = []
  for (const key of textColumns.value) {
    const value = (row.values[key] ?? "").trim()
    if (!value) continue
    parts.push(joinMode.value === "labeled" && textColumns.value.length > 1 ? `${titles.get(key) ?? key}：${value}` : value)
  }
  return parts.join("\n")
})

function use() {
  const f = file.value
  if (!f || activeRow.value === null || textColumns.value.length === 0) return
  emit(
    "pick",
    {
      kind: "row",
      file_id: f.id,
      sheet: isLines.value ? null : (sheet.value ?? null),
      header_row: isLines.value ? 0 : Number(headerRow.value),
      text_columns: [...textColumns.value],
      join_mode: joinMode.value,
      row_number: activeRow.value,
    },
    sampleText.value,
  )
  open.value = false
}
</script>

<template>
  <Drawer v-model:open="open" :width="760" title="从文件里挑一行">
    <div class="ws-picker">
      <div class="ws-picker__controls">
        <Select v-model="fileId" :options="fileOptions" placeholder="选择文件" aria-label="文件" width="280px" />
        <template v-if="file && !isLines">
          <Select v-model="sheet" :options="sheetOptions" aria-label="工作表" width="180px" />
          <Select v-model="headerRow" :options="headerOptions" aria-label="表头所在行" width="120px" />
        </template>
      </div>

      <EmptyState v-if="files.recent.length === 0" compact title="还没有上传过文件" description="先在首页上传一个文件，或者在左边直接粘贴样本。" />
      <p v-else-if="!file" class="ws-picker__hint">选择一个最近使用的文件，再点表头选文本列、点一行作为样本。</p>
      <div v-else-if="loading && !preview" class="ws-picker__skeleton">
        <Skeleton v-for="i in 6" :key="i" height="24px" />
      </div>
      <EmptyState v-else-if="loadError" tone="danger" compact title="预览没有加载出来" :description="(loadError as Error).message" />
      <PreviewGrid
        v-else-if="preview"
        :preview="preview"
        :selected="textColumns"
        :lines="isLines"
        selectable-rows
        :active-row="activeRow"
        max-height="360px"
        @toggle="toggle"
        @row-click="activeRow = $event"
      />

      <div v-if="preview" class="ws-picker__foot">
        <SegmentedControl
          v-if="textColumns.length > 1"
          v-model="joinModel"
          size="sm"
          aria-label="拼接方式"
          :options="[
            { value: 'labeled', label: '带列名' },
            { value: 'plain', label: '只拼值' },
          ]"
        />
        <pre class="ws-picker__sample">{{ sampleText || "点一行作为样本" }}</pre>
      </div>
    </div>
    <template #footer>
      <Button variant="secondary" @click="open = false">取消</Button>
      <Button variant="primary" :disabled="!sampleText" @click="use">使用这一行</Button>
    </template>
  </Drawer>
</template>

<style scoped>
.ws-picker {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-picker__controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.ws-picker__hint {
  margin: 0;
  color: var(--ink-2);
}

.ws-picker__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-picker__foot {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-picker__sample {
  max-height: 140px;
  margin: 0;
  padding: var(--space-3);
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--surface-2);
  font-family: var(--font-sans);
  white-space: pre-wrap;
}
</style>
