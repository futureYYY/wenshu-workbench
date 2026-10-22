<script setup lang="ts">
// 提示词工坊左栏：按任务类型分组，每组标题前一个线路色小圆点；默认模板带“默认”标记；
// 悬停菜单：设为默认、复制、删除。
import { Ellipsis, Plus } from "@lucide/vue"
import { RouterLink } from "vue-router"
import type { PromptTemplate, TaskType } from "@/api/types"
import { TASK_TYPE_LABEL, TASK_TYPES } from "@/api/types"
import Button from "@/components/base/Button.vue"
import DropdownMenu from "@/components/base/DropdownMenu.vue"
import IconButton from "@/components/base/IconButton.vue"
import type { MenuItem } from "@/components/base/types"
import { lineVar } from "@/design/palette"
import { usePromptsStore } from "@/stores/prompts"

defineProps<{ currentId: number | null }>()

const emit = defineEmits<{
  setDefault: [prompt: PromptTemplate]
  copy: [prompt: PromptTemplate]
  remove: [prompt: PromptTemplate]
  create: [task: TaskType]
}>()

const prompts = usePromptsStore()

function menu(p: PromptTemplate): MenuItem[] {
  return [
    { label: "设为默认", disabled: p.is_default, onSelect: () => emit("setDefault", p) },
    { label: "复制", onSelect: () => emit("copy", p) },
    { separator: true, label: "" },
    { label: p.is_builtin ? "内置模板不能删除" : "删除", danger: !p.is_builtin, disabled: p.is_builtin, onSelect: () => emit("remove", p) },
  ]
}

const createMenu: MenuItem[] = TASK_TYPES.map((t) => ({ label: `${TASK_TYPE_LABEL[t]}提示词`, onSelect: () => emit("create", t) }))
</script>

<template>
  <nav class="ws-plist" aria-label="提示词列表">
    <section v-for="task in TASK_TYPES" :key="task" class="ws-plist__group">
      <h2 class="ws-plist__heading">
        <span class="ws-plist__dot" :style="{ background: lineVar(task === 'classify' ? 0 : 1) }" aria-hidden="true" />
        {{ TASK_TYPE_LABEL[task] }}
      </h2>
      <ul class="ws-plist__items">
        <li v-for="p in prompts.byType(task)" :key="p.id" class="ws-plist__item" :class="{ 'is-current': p.id === currentId }">
          <RouterLink :to="`/prompts/${p.id}`" class="ws-plist__link" :aria-current="p.id === currentId ? 'page' : undefined">
            <span class="ws-plist__name">{{ p.name }}</span>
            <span v-if="p.is_default" class="ws-plist__tag">默认</span>
          </RouterLink>
          <span class="ws-plist__more">
            <DropdownMenu :items="menu(p)" align="start">
              <template #trigger>
                <IconButton :label="`“${p.name}”的更多操作`" size="sm">
                  <Ellipsis :size="16" :stroke-width="1.75" />
                </IconButton>
              </template>
            </DropdownMenu>
          </span>
        </li>
      </ul>
    </section>
    <DropdownMenu :items="createMenu" align="start">
      <template #trigger>
        <Button variant="secondary" size="sm">
          <template #icon><Plus :size="14" :stroke-width="1.75" /></template>
          新建提示词
        </Button>
      </template>
    </DropdownMenu>
  </nav>
</template>

<style scoped>
.ws-plist {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.ws-plist__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-plist__heading {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
  font-weight: 500;
}

.ws-plist__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-pill);
}

.ws-plist__items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-plist__item {
  position: relative;
  display: flex;
  align-items: center;
  border-radius: var(--radius-control);
}

.ws-plist__item:hover,
.ws-plist__item.is-current {
  background: var(--surface-2);
}

.ws-plist__item.is-current::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--ink);
}

.ws-plist__link {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  min-height: 34px;
  padding: 0 var(--space-2) 0 var(--space-3);
  border-radius: var(--radius-control);
  color: var(--ink);
  text-decoration: none;
}

.ws-plist__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-plist__item.is-current .ws-plist__name {
  font-weight: 500;
}

.ws-plist__tag {
  flex-shrink: 0;
  padding: 0 6px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  color: var(--ink-2);
  font-size: 11px;
  line-height: 18px;
}

.ws-plist__more {
  display: inline-flex;
  opacity: 0;
}

.ws-plist__item:hover .ws-plist__more,
.ws-plist__item:focus-within .ws-plist__more,
.ws-plist__more:has([data-state="open"]) {
  opacity: 1;
}
</style>
