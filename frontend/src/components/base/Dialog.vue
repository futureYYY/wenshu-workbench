<script setup lang="ts">
// 对话框（06 第 5.2 节）：只用于不可撤销的确认，宽 440 px；说明写清楚后果；主按钮写具体动作。
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "reka-ui"

const open = defineModel<boolean>("open", { default: false })

withDefaults(defineProps<{ title: string; description?: string; width?: number }>(), { width: 440 })
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="ws-dialog-overlay ws-overlay" />
      <DialogContent class="ws-dialog ws-popover" :style="{ width: `${width}px` }">
        <DialogTitle class="ws-dialog__title">{{ title }}</DialogTitle>
        <DialogDescription class="ws-dialog__desc" :class="{ 'sr-only': !description && !$slots.default }">
          <slot>{{ description ?? title }}</slot>
        </DialogDescription>
        <div class="ws-dialog__actions">
          <slot name="actions" />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style>
.ws-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-dialog);
  background: var(--overlay);
}

.ws-dialog {
  position: fixed;
  top: 28vh;
  left: 0;
  right: 0;
  z-index: var(--z-dialog);
  max-width: calc(100vw - 48px);
  margin: 0 auto;
  padding: var(--space-6);
  border: 1px solid var(--border);
  border-radius: var(--radius-drawer);
  background: var(--surface);
  box-shadow: var(--float-shadow);
  outline: none;
}

.ws-dialog__title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-lg);
  font-weight: 500;
}

.ws-dialog__desc {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-base);
  line-height: 1.7;
}

.ws-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-6);
}
</style>
