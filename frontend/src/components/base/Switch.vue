<script setup lang="ts">
// 开关（06 第 5.2 节）：36 × 20，开为墨色底。
const model = defineModel<boolean>({ default: false })

withDefaults(defineProps<{ disabled?: boolean; ariaLabel?: string; id?: string }>(), { disabled: false })

function toggle() {
  model.value = !model.value
}
</script>

<template>
  <button
    :id="id"
    type="button"
    role="switch"
    class="ws-switch"
    :class="{ 'is-on': model }"
    :aria-checked="model"
    :aria-label="ariaLabel"
    :disabled="disabled"
    @click="toggle"
  >
    <span class="ws-switch__thumb" aria-hidden="true" />
  </button>
</template>

<style scoped>
.ws-switch {
  position: relative;
  flex-shrink: 0;
  width: 36px;
  height: 20px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-pill);
  background: var(--border-strong);
  transition: background-color var(--dur-fast) var(--ease-out);
}

.ws-switch.is-on {
  background: var(--ink);
}

.ws-switch:disabled {
  opacity: 0.5;
}

.ws-switch__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: var(--radius-pill);
  background: var(--surface);
  transition: transform var(--dur-fast) var(--ease-out);
}

.ws-switch.is-on .ws-switch__thumb {
  transform: translateX(16px);
}
</style>
