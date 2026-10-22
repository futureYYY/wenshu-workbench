<script setup lang="ts">
// 第二站“选数据”：工作表、表头、数据预览与选列；选了多列时出现拼接方式；预览第一条拼接结果。
import { TriangleAlert } from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted } from "vue"
import Button from "@/components/base/Button.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Select from "@/components/base/Select.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import type { SelectOption } from "@/components/base/types"
import PreviewGrid from "@/components/data/PreviewGrid.vue"
import { useNewJobStore } from "@/stores/newJob"
import { useSettingsStore } from "@/stores/settings"
import { formatBytes, formatNumber } from "@/utils/format"

const props = defineProps<{ register: (fn?: () => void) => void }>()

const store = useNewJobStore()
const settings = useSettingsStore()

const sheetOptions = computed<SelectOption[]>(() =>
  (store.file?.sheets ?? []).map((s) => ({ value: s.name, label: s.name, hint: `${formatNumber(s.row_count)} 行` })),
)

const headerOptions = computed<SelectOption[]>(() => [
  { value: "0", label: "无表头" },
  ...Array.from({ length: 20 }, (_, i) => ({ value: String(i + 1), label: `第 ${i + 1} 行` })),
])

const sheetModel = computed({
  get: () => store.sheet ?? undefined,
  set: (value: string | undefined) => {
    if (value) void store.setSheet(value)
  },
})

const headerModel = computed({
  get: () => String(store.headerRow),
  set: (value: string | undefined) => {
    if (value !== undefined) void store.setHeaderRow(Number(value))
  },
})

const joinModel = computed({
  get: () => store.joinMode,
  set: (value: string) => {
    store.joinMode = value === "plain" ? "plain" : "labeled"
  },
})

const selectedTitles = computed(() => {
  const titles = new Map((store.preview?.columns ?? []).map((c) => [c.key, c.title]))
  return store.textColumns.map((k) => titles.get(k) ?? k)
})

const truncated = computed(() => !!store.preview?.truncated || !!store.file?.truncated)
const canNext = computed(() => store.textColumns.length > 0 && !!store.preview)

function next() {
  if (canNext.value) store.step = 2
}

onMounted(() => props.register(next))
onBeforeUnmount(() => props.register(undefined))
</script>

<template>
  <div v-if="store.file" class="ws-data">
    <div class="ws-data__head">
      <span class="ws-data__file">{{ store.file.original_name }}</span>
      <span class="ws-data__meta num">{{ formatBytes(store.file.size_bytes) }}</span>
      <span v-if="store.preview" class="ws-data__meta">共 <span class="num">{{ formatNumber(store.preview.total_rows) }}</span> 行</span>
      <span v-if="store.preview && store.preview.blank_rows > 0" class="ws-data__meta">
        其中空行 <span class="num">{{ formatNumber(store.preview.blank_rows) }}</span>
      </span>
      <Button variant="text" size="sm" class="ws-data__change" @click="store.step = 0">换文件</Button>
    </div>

    <div v-if="!store.isLines" class="ws-data__controls">
      <label class="ws-data__control">
        <span>工作表</span>
        <Select v-model="sheetModel" :options="sheetOptions" aria-label="工作表" width="240px" />
      </label>
      <label class="ws-data__control">
        <span>表头</span>
        <Select v-model="headerModel" :options="headerOptions" aria-label="表头所在行" width="140px" />
      </label>
    </div>

    <p v-if="truncated" class="ws-data__warn" role="status">
      <TriangleAlert :size="16" :stroke-width="2" aria-hidden="true" />
      只读取了前 {{ formatNumber(settings.limits.max_rows_per_source) }} 条
    </p>

    <div v-if="store.previewLoading && !store.preview" class="ws-data__skeleton">
      <Skeleton v-for="i in 8" :key="i" height="28px" />
    </div>
    <EmptyState
      v-else-if="store.previewError"
      tone="danger"
      title="预览没有加载出来"
      :description="(store.previewError as Error).message"
    >
      <Button variant="primary" @click="store.loadPreview()">重新加载</Button>
    </EmptyState>
    <PreviewGrid
      v-else-if="store.preview"
      :preview="store.preview"
      :selected="store.textColumns"
      :suggested="store.suggestedApplied"
      :lines="store.isLines"
      :class="{ 'is-loading': store.previewLoading }"
      @toggle="store.toggleColumn"
    />

    <div class="ws-data__foot">
      <div class="ws-data__picked">
        <p class="ws-data__picked-text">
          <template v-if="store.textColumns.length">已选 {{ store.textColumns.length }} 列：{{ selectedTitles.join("、") }}</template>
          <template v-else>点击表头选择要处理的文本列</template>
        </p>
        <SegmentedControl
          v-if="store.textColumns.length > 1"
          v-model="joinModel"
          size="sm"
          aria-label="拼接方式"
          :options="[
            { value: 'labeled', label: '带列名' },
            { value: 'plain', label: '只拼值' },
          ]"
        />
      </div>
      <div class="ws-data__sample">
        <p class="ws-data__sample-title">第一条将这样发给模型：</p>
        <pre class="ws-data__sample-box">{{ store.firstItemPreview || "（选好文本列后显示）" }}</pre>
      </div>
    </div>

    <div class="ws-data__actions">
      <Button variant="primary" :disabled="!canNext" @click="next">下一站：设任务</Button>
    </div>
  </div>
</template>

<style scoped>
.ws-data {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-data__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-4);
}

.ws-data__file {
  font-size: var(--text-lg);
  font-weight: 500;
}

.ws-data__meta {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-data__change {
  margin-left: auto;
}

.ws-data__controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
}

.ws-data__control {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--ink-2);
}

.ws-data__warn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--status-warn) 12%, transparent);
  color: var(--status-warn);
  font-size: var(--text-sm);
}

.ws-data__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.is-loading {
  opacity: 0.6;
}

.ws-data__foot {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-8);
}

.ws-data__picked {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.ws-data__picked-text {
  margin: 0;
}

.ws-data__sample-title {
  margin: 0 0 var(--space-2);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-data__sample-box {
  max-height: 160px;
  margin: 0;
  padding: var(--space-3) var(--space-4);
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--surface);
  font-family: var(--font-sans);
  font-size: var(--text-base);
  white-space: pre-wrap;
}

.ws-data__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
