<script setup lang="ts">
// 第一站“选文件”：与首页相同的拖放区域，下方两个标签页“最近文件”和“粘贴文本”（Ctrl+Enter 确认）。
import { onBeforeUnmount, onMounted, ref } from "vue"
import type { FileInfo } from "@/api/types"
import Button from "@/components/base/Button.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import Input from "@/components/base/Input.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import Tabs from "@/components/base/Tabs.vue"
import Textarea from "@/components/base/Textarea.vue"
import { useFileIntake, usePasteToStart } from "@/composables/useFileIntake"
import StartStation from "@/features/home/StartStation.vue"
import { useFilesStore } from "@/stores/files"
import { useNewJobStore } from "@/stores/newJob"
import { formatBytes, formatNumber, formatRelativeDate } from "@/utils/format"
import { notifyError } from "@/utils/toast"

const tab = defineModel<"recent" | "paste">("tab", { default: "recent" })
const props = defineProps<{ register: (fn?: () => void) => void }>()

const files = useFilesStore()
const store = useNewJobStore()
const { intakeText } = useFileIntake()

const text = ref("")
const name = ref("")
const submitting = ref(false)

usePasteToStart(() => tab.value !== "paste")

async function submitPaste() {
  if (submitting.value) return
  submitting.value = true
  try {
    await intakeText(text.value, name.value.trim() || undefined)
  } finally {
    submitting.value = false
  }
}

async function useFile(file: FileInfo) {
  try {
    await store.selectFile(file)
  } catch (e) {
    notifyError(e)
  }
}

function rows(file: FileInfo): number | null {
  if (file.kind === "lines") return file.line_count
  return file.sheets[0]?.row_count ?? null
}

onMounted(() => {
  void files.load(true).catch(() => undefined)
  props.register(() => {
    if (tab.value === "paste" && text.value.trim()) void submitPaste()
  })
})

onBeforeUnmount(() => props.register(undefined))
</script>

<template>
  <div class="ws-step">
    <StartStation compact :show-paste="false" :transition="false" />

    <div class="ws-step__panel">
      <Tabs
        v-model="tab"
        :items="[
          { value: 'recent', label: '最近文件' },
          { value: 'paste', label: '粘贴文本' },
        ]"
        id-prefix="file-tab"
        aria-label="选择数据来源"
      />

      <div v-if="tab === 'recent'" role="tabpanel" aria-labelledby="file-tab-recent" class="ws-step__body">
        <div v-if="!files.loaded && files.loading" class="ws-step__skeleton">
          <Skeleton v-for="i in 4" :key="i" height="20px" />
        </div>
        <EmptyState
          v-else-if="files.recent.length === 0"
          compact
          title="还没有上传过文件"
          description="把文件拖进上面的区域，或者换到“粘贴文本”直接粘贴。"
        />
        <ul v-else class="ws-files">
          <li v-for="file in files.recent" :key="file.id">
            <button type="button" class="ws-files__row" @click="useFile(file)">
              <span class="ws-files__name">{{ file.original_name }}</span>
              <span class="ws-files__ext num">{{ file.ext }}</span>
              <span class="ws-files__size num">{{ formatBytes(file.size_bytes) }}</span>
              <span class="ws-files__rows">
                <template v-if="rows(file) !== null"><span class="num">{{ formatNumber(rows(file)) }}</span> 行</template>
              </span>
              <span class="ws-files__time">{{ formatRelativeDate(file.last_used_at) }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div v-else role="tabpanel" aria-labelledby="file-tab-paste" class="ws-step__body ws-paste">
        <Textarea
          v-model="text"
          :rows="12"
          placeholder="每行一条数据。粘贴后按 Ctrl+Enter 开始"
          aria-label="粘贴文本"
          data-testid="paste-text"
          @submit="submitPaste"
        />
        <div class="ws-paste__foot">
          <Input v-model="name" placeholder="名称（可不填）" aria-label="名称" class="ws-paste__name" :maxlength="100" />
          <Button variant="primary" :loading="submitting" :disabled="!text.trim()" @click="submitPaste">开始</Button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ws-step {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: var(--form-max);
}

.ws-step__panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-step__body {
  min-height: 160px;
}

.ws-step__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-files {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-files__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 48px 80px 96px 72px;
  align-items: center;
  gap: var(--space-4);
  width: 100%;
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 0;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--ink);
  text-align: left;
}

.ws-files__row:hover {
  background: var(--surface-2);
}

.ws-files__name {
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-files__ext,
.ws-files__size,
.ws-files__rows,
.ws-files__time {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-files__time {
  text-align: right;
}

.ws-paste {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-paste__foot {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: var(--space-3);
}

.ws-paste__name {
  width: 280px;
}
</style>
