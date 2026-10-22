<script setup lang="ts">
// 弹出层（基于 Reka UI Popover）：圆角 10 px，浮层阴影，进入 140 ms（缩放 0.98→1 + 淡入）。
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui"

const open = defineModel<boolean>("open", { default: false })

withDefaults(
  defineProps<{
    side?: "top" | "right" | "bottom" | "left"
    align?: "start" | "center" | "end"
    width?: number
  }>(),
  { side: "bottom", align: "start", width: 360 },
)
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child>
      <slot name="trigger" />
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        :side="side"
        :align="align"
        :side-offset="6"
        class="ws-pop ws-popover"
        :style="{ width: `${width}px` }"
      >
        <slot />
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style>
.ws-pop {
  z-index: var(--z-popover);
  max-width: calc(100vw - 32px);
  max-height: min(70vh, var(--reka-popover-content-available-height, 70vh));
  overflow: auto;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-popover);
  background: var(--surface);
  box-shadow: var(--float-shadow);
  outline: none;
}
</style>
