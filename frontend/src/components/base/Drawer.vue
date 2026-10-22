<script setup lang="ts">
// 抽屉（06 第 5.2 节）：从右侧滑入，遮罩 --overlay；Esc 关闭；
// 打开时焦点进入第一个可交互元素，关闭时回到触发它的元素（Reka UI 的 Dialog 负责焦点管理）。
import { X } from "@lucide/vue"
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "reka-ui"

const open = defineModel<boolean>("open", { default: false })

withDefaults(
  defineProps<{
    title?: string
    description?: string
    width?: number
  }>(),
  { width: 640 },
)

const emit = defineEmits<{ closed: [] }>()

function onOpenChange(value: boolean) {
  open.value = value
  if (!value) emit("closed")
}
</script>

<template>
  <DialogRoot :open="open" @update:open="onOpenChange">
    <DialogPortal>
      <DialogOverlay class="ws-drawer-overlay ws-overlay" />
      <DialogContent class="ws-drawer" :style="{ width: `${width}px` }">
        <header class="ws-drawer__header">
          <div class="ws-drawer__heading">
            <DialogTitle class="ws-drawer__title">
              <slot name="title">{{ title }}</slot>
            </DialogTitle>
            <slot name="subtitle" />
          </div>
          <div class="ws-drawer__actions">
            <slot name="actions" />
            <DialogClose class="ws-drawer__close" aria-label="关闭">
              <X :size="18" :stroke-width="1.75" aria-hidden="true" />
            </DialogClose>
          </div>
        </header>
        <DialogDescription class="sr-only">{{ description ?? title ?? "详情" }}</DialogDescription>
        <div class="ws-drawer__body">
          <slot />
        </div>
        <footer v-if="$slots.footer" class="ws-drawer__footer">
          <slot name="footer" />
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style>
.ws-drawer-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-drawer);
  background: var(--overlay);
}

.ws-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: var(--z-drawer);
  display: flex;
  flex-direction: column;
  max-width: calc(100vw - 96px);
  border-left: 1px solid var(--border);
  border-radius: var(--radius-drawer) 0 0 var(--radius-drawer);
  background: var(--surface);
  box-shadow: var(--float-shadow);
  outline: none;
}

.ws-drawer[data-state="open"] {
  animation: ws-drawer-in var(--dur-base) var(--ease-out);
}

.ws-drawer[data-state="closed"] {
  animation: ws-drawer-out 180ms var(--ease-in);
}

.ws-drawer__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-5) var(--space-6) var(--space-4);
  border-bottom: 1px solid var(--border);
}

.ws-drawer__heading {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.ws-drawer__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 500;
  line-height: 1.6;
}

.ws-drawer__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.ws-drawer__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--ink-2);
}

.ws-drawer__close:hover {
  background: var(--surface-2);
  color: var(--ink);
}

.ws-drawer__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
}

.ws-drawer__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border);
}
</style>
