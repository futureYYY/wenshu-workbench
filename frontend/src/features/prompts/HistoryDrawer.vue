<script setup lang="ts">
// 版本历史抽屉（06 第 6.7 节）：版本列表（版本号、时间、说明），点击某版本只读预览，底部“恢复此版本”。
import { computed, ref, watch } from "vue"
import { promptsApi } from "@/api/endpoints"
import type { PromptTemplate, PromptVariable, PromptVersionDetail, PromptVersionSummary, TaskType } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Drawer from "@/components/base/Drawer.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import PromptEditor from "@/components/editor/PromptEditor.vue"
import { formatDateTime } from "@/utils/format"
import { notify, notifyError } from "@/utils/toast"

const open = defineModel<boolean>("open", { default: false })

const props = defineProps<{
  promptId: number
  taskType: TaskType
  currentVersion: number
  variables: PromptVariable[]
}>()

const emit = defineEmits<{ restored: [prompt: PromptTemplate] }>()

const versions = ref<PromptVersionSummary[]>([])
const loading = ref(false)
const loadError = ref<unknown>(null)
const selected = ref<PromptVersionDetail | null>(null)
const selectedLoading = ref(false)
const restoring = ref(false)

async function loadList() {
  loading.value = true
  loadError.value = null
  try {
    versions.value = await promptsApi.versions(props.promptId)
    const first = versions.value.find((v) => v.version !== props.currentVersion) ?? versions.value[0]
    if (first) void select(first.version)
  } catch (e) {
    loadError.value = e
  } finally {
    loading.value = false
  }
}

async function select(version: number) {
  selectedLoading.value = true
  try {
    selected.value = await promptsApi.version(props.promptId, version)
  } catch (e) {
    notifyError(e)
  } finally {
    selectedLoading.value = false
  }
}

watch(open, (value) => {
  if (value) {
    selected.value = null
    void loadList()
  }
})

async function restore() {
  const v = selected.value
  if (!v || restoring.value) return
  restoring.value = true
  try {
    const next = await promptsApi.restore(props.promptId, v.version)
    notify(`已恢复为 v${v.version}（新版本 v${next.version}）`)
    emit("restored", next)
    open.value = false
  } catch (e) {
    notifyError(e)
  } finally {
    restoring.value = false
  }
}

const snapshot = computed(() => selected.value?.snapshot ?? null)
const noop = (_value: string) => undefined
</script>

<template>
  <Drawer v-model:open="open" :width="760" title="版本历史">
    <div class="ws-history">
      <div class="ws-history__list">
        <div v-if="loading" class="ws-history__skeleton">
          <Skeleton v-for="i in 5" :key="i" height="40px" />
        </div>
        <EmptyState v-else-if="loadError" tone="danger" compact title="版本列表没有加载出来" :description="(loadError as Error).message" />
        <ul v-else class="ws-history__items">
          <li v-for="v in versions" :key="v.version">
            <button
              type="button"
              class="ws-history__item"
              :class="{ 'is-active': selected?.version === v.version }"
              :aria-pressed="selected?.version === v.version"
              @click="select(v.version)"
            >
              <span class="ws-history__ver num">v{{ v.version }}</span>
              <span class="ws-history__time">{{ formatDateTime(v.created_at) }}</span>
              <span v-if="v.version === currentVersion" class="ws-history__tag">当前</span>
              <span class="ws-history__note">{{ v.note || "没有说明" }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="ws-history__preview">
        <div v-if="selectedLoading && !snapshot" class="ws-history__skeleton">
          <Skeleton height="160px" />
        </div>
        <template v-else-if="snapshot">
          <p class="ws-history__title">v{{ selected?.version }} {{ snapshot.name }}</p>
          <PromptEditor
            :model-value="snapshot.system_prompt"
            label="系统提示词"
            template-slot="system"
            :variables="variables"
            readonly
            @update:model-value="noop"
          />
          <PromptEditor
            :model-value="snapshot.user_template"
            label="用户消息模板"
            template-slot="user"
            :variables="variables"
            readonly
            @update:model-value="noop"
          />
          <template v-if="taskType === 'summarize'">
            <PromptEditor
              :model-value="snapshot.chunk_template ?? ''"
              label="分段模板"
              template-slot="chunk"
              :variables="variables"
              readonly
              @update:model-value="noop"
            />
            <PromptEditor
              :model-value="snapshot.merge_template ?? ''"
              label="合并模板"
              template-slot="merge"
              :variables="variables"
              readonly
              @update:model-value="noop"
            />
          </template>
        </template>
        <p v-else class="ws-history__muted">选择左边的一个版本查看内容</p>
      </div>
    </div>
    <template #footer>
      <Button variant="secondary" @click="open = false">关闭</Button>
      <Button
        variant="primary"
        :disabled="!selected || selected.version === currentVersion"
        :loading="restoring"
        @click="restore"
      >
        恢复此版本
      </Button>
    </template>
  </Drawer>
</template>

<style scoped>
.ws-history {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: var(--space-5);
  min-height: 100%;
}

.ws-history__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-history__items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-history__item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 2px var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--ink);
  text-align: left;
}

.ws-history__item:hover,
.ws-history__item.is-active {
  background: var(--surface-2);
}

.ws-history__item.is-active {
  box-shadow: inset 2px 0 0 var(--ink);
}

.ws-history__ver {
  font-weight: 700;
}

.ws-history__time {
  color: var(--ink-2);
  font-size: var(--text-xs);
  align-self: center;
}

.ws-history__tag {
  padding: 0 6px;
  border-radius: var(--radius-pill);
  background: var(--ink);
  color: var(--on-ink);
  font-size: 11px;
  line-height: 18px;
}

.ws-history__note {
  grid-column: 1 / -1;
  overflow: hidden;
  color: var(--ink-2);
  font-size: var(--text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-history__preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

.ws-history__title {
  margin: 0;
  font-weight: 500;
}

.ws-history__muted {
  margin: 0;
  color: var(--ink-2);
}
</style>
