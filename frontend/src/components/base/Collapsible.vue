<script setup lang="ts">
// 折叠面板：标题行显示当前取值摘要；高度过渡 --dur-slow、--ease-move（06 第 8.2 节）。
import { ChevronRight } from "@lucide/vue"
import { useId } from "vue"

const open = defineModel<boolean>("open", { default: false })

defineProps<{ title: string; summary?: string }>()

const panelId = useId()
</script>

<template>
  <section class="ws-collapse" :class="{ 'is-open': open }">
    <button
      type="button"
      class="ws-collapse__head"
      :aria-expanded="open"
      :aria-controls="panelId"
      @click="open = !open"
    >
      <ChevronRight class="ws-collapse__chevron" :size="16" :stroke-width="1.75" aria-hidden="true" />
      <span class="ws-collapse__title">{{ title }}</span>
      <span v-if="summary" class="ws-collapse__summary">{{ summary }}</span>
    </button>
    <div :id="panelId" class="ws-collapse__panel" role="region" :aria-hidden="!open" :inert="!open || undefined">
      <div class="ws-collapse__inner">
        <div class="ws-collapse__content">
          <slot />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ws-collapse__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  min-height: 36px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: var(--text-base);
  font-weight: 500;
  text-align: left;
}

.ws-collapse__chevron {
  flex-shrink: 0;
  color: var(--ink-2);
  transition: transform var(--dur-base) var(--ease-move);
}

.ws-collapse.is-open .ws-collapse__chevron {
  transform: rotate(90deg);
}

.ws-collapse__summary {
  overflow: hidden;
  color: var(--ink-2);
  font-size: var(--text-sm);
  font-weight: 400;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-collapse__panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--dur-slow) var(--ease-move);
}

.ws-collapse.is-open .ws-collapse__panel {
  grid-template-rows: 1fr;
}

.ws-collapse__inner {
  min-height: 0;
  overflow: hidden;
}

.ws-collapse__content {
  padding: var(--space-2) 0 var(--space-3) var(--space-6);
}
</style>
