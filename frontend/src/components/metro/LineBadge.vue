<script setup lang="ts">
// 线路徽标（06 第 5.1 节）：实心胶囊，底色为线路色，文字颜色按对比度自动选择；可带计数；
// 最长 160 px，超出省略，悬停 400 ms 后显示全名。
import { computed } from "vue"
import Tooltip from "@/components/base/Tooltip.vue"
import { lineStyle } from "@/design/palette"
import { useUiStore } from "@/stores/ui"
import { formatNumber } from "@/utils/format"

const props = withDefaults(
  defineProps<{
    label: string
    colorIndex: number
    size?: "sm" | "md"
    count?: number | null
    selected?: boolean
    tooltip?: boolean
  }>(),
  { size: "sm", count: null, selected: false, tooltip: true },
)

const ui = useUiStore()
const style = computed(() => lineStyle(props.colorIndex, ui.resolvedTheme))
const css = computed(() => ({
  background: style.value.color,
  color: style.value.text,
  boxShadow: style.value.stroke ? `inset 0 0 0 1px ${style.value.stroke}` : undefined,
}))
</script>

<template>
  <Tooltip :content="label" :disabled="!tooltip">
    <span class="ws-badge" :class="[`ws-badge--${size}`, { 'is-selected': selected }]" :style="css">
      <span class="ws-badge__text">{{ label }}</span>
      <template v-if="count !== null">
        <span class="ws-badge__sep" aria-hidden="true" />
        <span class="ws-badge__count num">{{ formatNumber(count) }}</span>
      </template>
    </span>
  </Tooltip>
</template>

<style scoped>
.ws-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 160px;
  padding: 0 10px;
  border-radius: var(--radius-pill);
  font-size: var(--text-sm);
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  vertical-align: middle;
}

.ws-badge--sm {
  height: 22px;
}

.ws-badge--md {
  height: 26px;
}

.ws-badge.is-selected {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

.ws-badge__text {
  overflow: hidden;
  text-overflow: ellipsis;
}

.ws-badge__sep {
  align-self: stretch;
  width: 1px;
  margin: 5px 0;
  background: currentColor;
  opacity: 0.45;
}

.ws-badge__count {
  font-size: var(--text-xs);
}
</style>
