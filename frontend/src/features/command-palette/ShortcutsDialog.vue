<script setup lang="ts">
// 快捷键一览（按 ? 打开）。
import { X } from "@lucide/vue"
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "reka-ui"
import Kbd from "@/components/base/Kbd.vue"
import { useUiStore } from "@/stores/ui"
import { shortcutKeys } from "@/utils/keyboard"
import { SHORTCUTS } from "./shortcuts"

const ui = useUiStore()
</script>

<template>
  <DialogRoot v-model:open="ui.shortcutsOpen">
    <DialogPortal>
      <DialogOverlay class="ws-dialog-overlay ws-overlay" />
      <DialogContent class="ws-keys ws-popover">
        <header class="ws-keys__head">
          <DialogTitle class="ws-keys__title">快捷键</DialogTitle>
          <DialogClose class="ws-keys__close" aria-label="关闭">
            <X :size="18" :stroke-width="1.75" aria-hidden="true" />
          </DialogClose>
        </header>
        <DialogDescription class="sr-only">文枢的全部键盘快捷键</DialogDescription>
        <table class="ws-keys__table">
          <thead>
            <tr>
              <th scope="col">按键</th>
              <th scope="col">作用</th>
              <th scope="col">范围</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in SHORTCUTS" :key="i">
              <td class="ws-keys__keys">
                <template v-for="(spec, j) in row.keys" :key="spec">
                  <span v-if="j > 0" class="ws-keys__or">或</span>
                  <span class="ws-keys__combo">
                    <Kbd v-for="k in shortcutKeys(spec)" :key="k">{{ k }}</Kbd>
                  </span>
                </template>
              </td>
              <td>{{ row.action }}</td>
              <td class="ws-keys__scope">{{ row.scope }}</td>
            </tr>
          </tbody>
        </table>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style>
.ws-keys {
  position: fixed;
  top: 10vh;
  left: 0;
  right: 0;
  z-index: var(--z-dialog);
  width: 640px;
  max-width: calc(100vw - 48px);
  max-height: 80vh;
  margin: 0 auto;
  overflow-y: auto;
  padding: var(--space-6);
  border: 1px solid var(--border);
  border-radius: var(--radius-drawer);
  background: var(--surface);
  box-shadow: var(--float-shadow);
  outline: none;
}

.ws-keys__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.ws-keys__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 500;
}

.ws-keys__close {
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

.ws-keys__close:hover {
  background: var(--surface-2);
}

.ws-keys__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.ws-keys__table th {
  padding: 0 0 var(--space-2);
  color: var(--ink-2);
  font-size: var(--text-xs);
  font-weight: 500;
  text-align: left;
}

.ws-keys__table td {
  padding: var(--space-2) var(--space-3) var(--space-2) 0;
  border-top: 1px solid var(--border);
  vertical-align: middle;
}

.ws-keys__keys {
  white-space: nowrap;
}

.ws-keys__combo {
  display: inline-flex;
  gap: 2px;
}

.ws-keys__or {
  margin: 0 6px;
  color: var(--ink-2);
}

.ws-keys__scope {
  color: var(--ink-2);
}
</style>
