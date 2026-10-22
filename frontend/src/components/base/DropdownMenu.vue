<script setup lang="ts">
// 下拉菜单（基于 Reka UI DropdownMenu）：圆角 10 px，浮层阴影，进入 140 ms。
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "reka-ui"
import { shortcutKeys } from "@/utils/keyboard"
import Kbd from "./Kbd.vue"
import type { MenuItem } from "./types"

withDefaults(
  defineProps<{
    items: MenuItem[]
    align?: "start" | "center" | "end"
    side?: "top" | "right" | "bottom" | "left"
  }>(),
  { align: "end", side: "bottom" },
)

const open = defineModel<boolean>("open", { default: false })
</script>

<template>
  <DropdownMenuRoot v-model:open="open" :modal="false">
    <DropdownMenuTrigger as-child>
      <slot name="trigger" />
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent :align="align" :side="side" :side-offset="6" class="ws-menu ws-popover">
        <template v-for="(item, i) in items" :key="item.key ?? `${i}-${item.label}`">
          <DropdownMenuSeparator v-if="item.separator" class="ws-menu__sep" />
          <DropdownMenuLabel v-else-if="item.heading" class="ws-menu__label">{{ item.label }}</DropdownMenuLabel>
          <DropdownMenuItem
            v-else
            class="ws-menu__item"
            :class="{ 'is-danger': item.danger }"
            :disabled="item.disabled"
            @select="item.onSelect?.()"
          >
            <component :is="item.icon" v-if="item.icon" :size="16" :stroke-width="1.75" aria-hidden="true" />
            <span class="ws-menu__text">{{ item.label }}</span>
            <span v-if="item.shortcut" class="ws-menu__keys">
              <Kbd v-for="k in shortcutKeys(item.shortcut)" :key="k">{{ k }}</Kbd>
            </span>
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

<style>
.ws-menu {
  z-index: var(--z-popover);
  min-width: 180px;
  padding: var(--space-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-popover);
  background: var(--surface);
  box-shadow: var(--float-shadow);
}

.ws-menu__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 32px;
  padding: 0 var(--space-3);
  border-radius: 6px;
  color: var(--ink);
  font-size: var(--text-base);
  cursor: pointer;
  outline: none;
  user-select: none;
}

.ws-menu__item[data-highlighted] {
  background: var(--surface-2);
}

.ws-menu__item[data-disabled] {
  color: var(--ink-3);
  cursor: not-allowed;
}

.ws-menu__item.is-danger {
  color: var(--status-danger);
}

.ws-menu__text {
  flex: 1;
  white-space: nowrap;
}

.ws-menu__keys {
  display: inline-flex;
  gap: 2px;
  margin-left: var(--space-4);
}

.ws-menu__sep {
  height: 1px;
  margin: var(--space-1) 0;
  background: var(--border);
}

.ws-menu__label {
  padding: 6px var(--space-3) 2px;
  color: var(--ink-2);
  font-size: var(--text-xs);
}
</style>
