<script setup lang="ts">
// 下拉选择（基于 Reka UI Select，06 第 5.2 节）：选项高 32 px，当前项左边 2 px 墨色竖条。
// 值一律用字符串；数字 id 由调用方转换。
import { ChevronDown } from "@lucide/vue"
import {
  SelectContent,
  SelectItem,
  SelectItemText,
  SelectPortal,
  SelectRoot,
  SelectTrigger,
  SelectValue,
  SelectViewport,
} from "reka-ui"
import type { SelectOption } from "./types"

const model = defineModel<string | undefined>()

withDefaults(
  defineProps<{
    options: SelectOption[]
    placeholder?: string
    disabled?: boolean
    ariaLabel?: string
    id?: string
    size?: "sm" | "md"
    width?: string
  }>(),
  { placeholder: "请选择", size: "md" },
)

function onUpdate(value: unknown) {
  if (value === null || value === undefined) return
  model.value = String(value)
}
</script>

<template>
  <SelectRoot :model-value="model" :disabled="disabled" @update:model-value="onUpdate">
    <SelectTrigger
      :id="id"
      class="ws-select"
      :class="`ws-select--${size}`"
      :aria-label="ariaLabel"
      :style="width ? { width } : undefined"
    >
      <SelectValue :placeholder="placeholder" class="ws-select__value" />
      <ChevronDown class="ws-select__chevron" :size="16" :stroke-width="1.75" aria-hidden="true" />
    </SelectTrigger>
    <SelectPortal>
      <SelectContent position="popper" :side-offset="6" class="ws-select-content ws-popover">
        <SelectViewport class="ws-select-viewport">
          <SelectItem
            v-for="opt in options"
            :key="opt.value"
            :value="opt.value"
            :disabled="opt.disabled"
            class="ws-select-item"
          >
            <span class="ws-select-item__main">
              <SelectItemText>{{ opt.label }}</SelectItemText>
              <span v-if="opt.description" class="ws-select-item__desc">{{ opt.description }}</span>
            </span>
            <span v-if="opt.hint" class="ws-select-item__hint num">{{ opt.hint }}</span>
          </SelectItem>
        </SelectViewport>
      </SelectContent>
    </SelectPortal>
  </SelectRoot>
</template>

<style scoped>
.ws-select {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-width: 160px;
  height: 36px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
  font-size: var(--text-base);
  text-align: left;
}

.ws-select--sm {
  height: 28px;
  min-width: 120px;
  padding: 0 var(--space-2);
  font-size: var(--text-sm);
}

.ws-select:hover:not([data-disabled]) {
  background: var(--surface-2);
}

.ws-select[data-disabled] {
  opacity: 0.5;
  cursor: not-allowed;
}

.ws-select__value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-select[data-placeholder] .ws-select__value {
  color: var(--ink-2);
}

.ws-select__chevron {
  flex-shrink: 0;
  color: var(--ink-2);
  transition: transform var(--dur-fast) var(--ease-out);
}

.ws-select[data-state="open"] .ws-select__chevron {
  transform: rotate(180deg);
}
</style>

<style>
/* 弹出内容挂在 body 上，不能用 scoped */
.ws-select-content {
  z-index: var(--z-popover);
  min-width: var(--reka-select-trigger-width);
  max-height: min(360px, var(--reka-select-content-available-height));
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-popover);
  background: var(--surface);
  box-shadow: var(--float-shadow);
}

.ws-select-viewport {
  padding: var(--space-1);
}

.ws-select-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 32px;
  padding: 4px var(--space-3) 4px var(--space-4);
  border-radius: 6px;
  color: var(--ink);
  font-size: var(--text-base);
  cursor: pointer;
  outline: none;
  user-select: none;
}

.ws-select-item[data-highlighted] {
  background: var(--surface-2);
}

.ws-select-item[data-state="checked"]::before {
  content: "";
  position: absolute;
  left: 4px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  border-radius: 2px;
  background: var(--ink);
}

.ws-select-item[data-state="checked"] {
  font-weight: 500;
}

.ws-select-item[data-disabled] {
  color: var(--ink-3);
  cursor: not-allowed;
}

.ws-select-item__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ws-select-item__desc {
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-select-item__hint {
  flex-shrink: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}
</style>
