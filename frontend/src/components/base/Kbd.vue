<script setup lang="ts">
// 键帽：1 px 描边，底边 2 px，圆角 4 px，Overpass 12 px。inverse 用于墨色底的提示里。
defineProps<{ inverse?: boolean }>()
</script>

<template>
  <kbd class="ws-kbd num" :class="{ 'ws-kbd--inverse': inverse }"><slot /></kbd>
</template>

<style scoped>
.ws-kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border: 1px solid var(--border-strong);
  border-bottom-width: 2px;
  border-radius: var(--radius-kbd);
  background: var(--surface);
  color: var(--ink-2);
  font-size: var(--text-xs);
  font-weight: 500;
  line-height: 1;
}

.ws-kbd--inverse {
  background: transparent;
  color: var(--on-ink);
  border-color: color-mix(in srgb, var(--on-ink) 40%, transparent);
}
</style>
