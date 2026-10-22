<script setup lang="ts">
// 表单的一行：左边标签，右边控件，下方说明。
defineProps<{ label: string; for?: string; hint?: string; align?: "center" | "start" }>()
</script>

<template>
  <div class="ws-field" :class="align === 'start' ? 'is-start' : ''">
    <label class="ws-field__label" :for="$props.for">{{ label }}</label>
    <div class="ws-field__control">
      <slot />
      <p v-if="hint || $slots.hint" class="ws-field__hint">
        <slot name="hint">{{ hint }}</slot>
      </p>
    </div>
  </div>
</template>

<style scoped>
.ws-field {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  align-items: center;
  gap: var(--space-4);
  min-height: 36px;
}

.ws-field.is-start {
  align-items: start;
}

.ws-field.is-start .ws-field__label {
  padding-top: 8px;
}

.ws-field__label {
  color: var(--ink-2);
  font-size: var(--text-base);
}

.ws-field__control {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.ws-field__hint {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-xs);
}
</style>
