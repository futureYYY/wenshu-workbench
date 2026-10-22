<script setup lang="ts">
// 提示（06 第 5.2 节）：墨色底、12 px、圆角 6 px；悬停 400 ms 后出现；可附带快捷键键帽。
import { TooltipContent, TooltipPortal, TooltipRoot, TooltipTrigger } from "reka-ui"
import { computed, useSlots } from "vue"
import { shortcutKeys } from "@/utils/keyboard"
import Kbd from "./Kbd.vue"

const props = withDefaults(
  defineProps<{
    content?: string
    shortcut?: string
    side?: "top" | "right" | "bottom" | "left"
    disabled?: boolean
    delay?: number
  }>(),
  { side: "top", delay: 400 },
)

const slots = useSlots()
const empty = computed(() => !props.content && !slots.content && !props.shortcut)
const keys = computed(() => (props.shortcut ? shortcutKeys(props.shortcut) : []))
</script>

<template>
  <TooltipRoot :delay-duration="delay" :disabled="disabled || empty">
    <TooltipTrigger as-child>
      <slot />
    </TooltipTrigger>
    <TooltipPortal>
      <TooltipContent :side="side" :side-offset="6" class="ws-tooltip ws-popover">
        <slot name="content">{{ content }}</slot>
        <span v-if="keys.length" class="ws-tooltip__keys">
          <Kbd v-for="k in keys" :key="k" inverse>{{ k }}</Kbd>
        </span>
      </TooltipContent>
    </TooltipPortal>
  </TooltipRoot>
</template>

<style>
/* 提示内容挂在 body 上，不用 scoped */
.ws-tooltip {
  z-index: var(--z-popover);
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  max-width: 320px;
  padding: 6px 10px;
  border-radius: var(--radius-tooltip);
  background: var(--ink);
  color: var(--on-ink);
  font-size: var(--text-xs);
  line-height: 1.5;
  box-shadow: var(--float-shadow);
  user-select: none;
}

.ws-tooltip__keys {
  display: inline-flex;
  gap: 2px;
}
</style>
