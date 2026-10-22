<script setup lang="ts">
// 图标按钮：32 px 见方，必须有 aria-label 和提示（06 第 5.2 节）。
// inheritAttrs 关掉、把 $attrs 绑到内部按钮上：作为下拉菜单、弹出层触发器（as-child）时，事件和属性能落到按钮上。
import Tooltip from "./Tooltip.vue"

defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    label: string
    shortcut?: string
    disabled?: boolean
    size?: "sm" | "md"
    pressed?: boolean
    tooltipSide?: "top" | "right" | "bottom" | "left"
  }>(),
  { size: "md", disabled: false, tooltipSide: "top" },
)
</script>

<template>
  <Tooltip :content="label" :shortcut="shortcut" :side="tooltipSide">
    <button
      type="button"
      v-bind="$attrs"
      class="ws-icon-btn"
      :class="[`ws-icon-btn--${size}`, { 'is-pressed': pressed }]"
      :aria-label="label"
      :aria-pressed="pressed === undefined ? undefined : pressed"
      :disabled="disabled"
    >
      <slot />
    </button>
  </Tooltip>
</template>

<style scoped>
.ws-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--ink-2);
  transition:
    background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out),
    transform var(--dur-press) var(--ease-out);
}

.ws-icon-btn--md {
  width: 32px;
  height: 32px;
}

.ws-icon-btn--sm {
  width: 28px;
  height: 28px;
}

.ws-icon-btn:hover:not(:disabled),
.ws-icon-btn[data-state="open"],
.ws-icon-btn.is-pressed {
  background: var(--surface-2);
  color: var(--ink);
}

.ws-icon-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.ws-icon-btn:disabled {
  opacity: 0.4;
}
</style>
