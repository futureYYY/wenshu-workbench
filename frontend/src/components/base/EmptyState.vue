<script setup lang="ts">
// 空状态：一小段线路（一条短线 + 一个空心站点）+ 一句标题 + 一句说明 + 一个主按钮。
withDefaults(defineProps<{ title: string; description?: string; compact?: boolean; tone?: "neutral" | "danger" }>(), {
  tone: "neutral",
})
</script>

<template>
  <div class="ws-empty" :class="{ 'is-compact': compact, 'is-danger': tone === 'danger' }">
    <svg class="ws-empty__art" width="88" height="20" viewBox="0 0 88 20" aria-hidden="true">
      <line x1="4" y1="10" x2="66" y2="10" class="ws-empty__line" />
      <circle cx="76" cy="10" r="6.5" class="ws-empty__station" />
    </svg>
    <p class="ws-empty__title">{{ title }}</p>
    <p v-if="description" class="ws-empty__desc">{{ description }}</p>
    <div v-if="$slots.default" class="ws-empty__actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.ws-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.ws-empty.is-compact {
  padding: var(--space-6) var(--space-4);
}

.ws-empty__art {
  margin-bottom: var(--space-2);
}

.ws-empty__line {
  stroke: var(--border-strong);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 6 4;
}

.ws-empty__station {
  fill: var(--surface);
  stroke: var(--border-strong);
  stroke-width: 3;
}

.ws-empty.is-danger .ws-empty__line,
.ws-empty.is-danger .ws-empty__station {
  stroke: var(--status-danger);
}

.ws-empty__title {
  margin: 0;
  color: var(--ink);
  font-size: var(--text-md);
  font-weight: 500;
}

.ws-empty__desc {
  max-width: 440px;
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-empty__actions {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-3);
}
</style>
