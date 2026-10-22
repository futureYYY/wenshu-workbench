<script setup lang="ts">
// 按钮（06 第 5.2 节）：主按钮墨色底；次按钮描边；文字按钮无底无框；危险按钮只在确认删除时使用。
// 加载中文字不变，底边出现一条来回移动的细线，按钮禁用。
withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "text" | "danger"
    size?: "sm" | "md" | "lg"
    loading?: boolean
    disabled?: boolean
    type?: "button" | "submit" | "reset"
    block?: boolean
  }>(),
  { variant: "secondary", size: "md", loading: false, disabled: false, type: "button", block: false },
)
</script>

<template>
  <button
    :type="type"
    class="ws-btn"
    :class="[`ws-btn--${variant}`, `ws-btn--${size}`, { 'is-loading': loading, 'ws-btn--block': block }]"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span class="ws-btn__content">
      <slot name="icon" />
      <slot />
    </span>
    <span v-if="loading" class="ws-btn__bar" aria-hidden="true"><span class="ws-shuttle" /></span>
  </button>
</template>

<style scoped>
.ws-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  gap: var(--space-2);
  border-radius: var(--radius-control);
  border: 1px solid transparent;
  font-family: var(--font-sans);
  font-size: var(--text-base);
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out),
    transform var(--dur-press) var(--ease-out);
}

.ws-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.ws-btn--sm {
  height: 28px;
  padding: 0 var(--space-3);
  font-size: var(--text-sm);
}

.ws-btn--md {
  height: 36px;
  padding: 0 var(--space-4);
}

.ws-btn--lg {
  height: 44px;
  padding: 0 var(--space-5);
}

.ws-btn--block {
  width: 100%;
}

.ws-btn__content {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.ws-btn--primary {
  background: var(--ink);
  color: var(--on-ink);
}

.ws-btn--primary:hover:not(:disabled) {
  background: color-mix(in oklab, var(--ink) 88%, var(--surface));
}

.ws-btn--secondary {
  background: var(--surface);
  border-color: var(--border-strong);
  color: var(--ink);
}

.ws-btn--secondary:hover:not(:disabled) {
  background: var(--surface-2);
}

.ws-btn--text {
  background: transparent;
  color: var(--ink);
  padding-left: var(--space-2);
  padding-right: var(--space-2);
}

.ws-btn--text:hover:not(:disabled) {
  background: var(--surface-2);
}

.ws-btn--danger {
  background: var(--surface);
  border-color: var(--border-strong);
  color: var(--status-danger);
}

.ws-btn--danger:hover:not(:disabled) {
  background: var(--surface-2);
}

.ws-btn:disabled:not(.is-loading) {
  opacity: 0.5;
}

.ws-btn__bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  overflow: hidden;
}

.ws-btn__bar > span {
  display: block;
  width: 40%;
  height: 100%;
  background: currentColor;
  animation: ws-shuttle 1.1s var(--ease-move) infinite alternate;
}
</style>
