<script setup lang="ts">
// 浓缩计（06 第 5.1 节）：上面一条代表原文字数（--ink-3），下面一条代表摘要字数（--ink），
// 长度按对数比例，最长 240 px；右侧是“压缩 15×”（导视数字 20 px）。
import { computed } from "vue"
import { formatNumber, formatRatio } from "@/utils/format"

const props = withDefaults(
  defineProps<{
    inputChars: number
    outputChars: number
    ratio?: number | null
    maxLength?: number
    label?: string
  }>(),
  { ratio: null, maxLength: 240, label: "压缩" },
)

const scaleMax = computed(() => Math.max(props.inputChars, props.outputChars, 1))

function length(chars: number): number {
  if (chars <= 0) return 0
  return Math.max(4, (Math.log10(chars + 1) / Math.log10(scaleMax.value + 1)) * props.maxLength)
}

const inputLen = computed(() => length(props.inputChars))
const outputLen = computed(() => length(props.outputChars))
const ratioValue = computed(() => {
  if (props.ratio !== null && props.ratio !== undefined) return props.ratio
  return props.outputChars > 0 ? props.inputChars / props.outputChars : null
})
const aria = computed(
  () => `原文 ${formatNumber(props.inputChars)} 字，摘要 ${formatNumber(props.outputChars)} 字，${props.label} ${formatRatio(ratioValue.value)}`,
)
</script>

<template>
  <div class="ws-gauge" role="img" :aria-label="aria">
    <div class="ws-gauge__rows">
      <div class="ws-gauge__row">
        <span class="ws-gauge__name">原文 <span class="num">{{ formatNumber(inputChars) }}</span> 字</span>
        <span class="ws-gauge__bar is-input" :style="{ width: `${inputLen}px` }" />
      </div>
      <div class="ws-gauge__row">
        <span class="ws-gauge__name">摘要 <span class="num">{{ formatNumber(outputChars) }}</span> 字</span>
        <span class="ws-gauge__bar is-output" :style="{ width: `${outputLen}px` }" />
      </div>
    </div>
    <div class="ws-gauge__ratio">
      <span class="ws-gauge__ratio-label">{{ label }}</span>
      <span class="ws-gauge__ratio-value num">{{ formatRatio(ratioValue) }}</span>
    </div>
  </div>
</template>

<style scoped>
.ws-gauge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-6);
}

.ws-gauge__rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-gauge__row {
  display: grid;
  grid-template-columns: 120px auto;
  align-items: center;
  gap: var(--space-3);
}

.ws-gauge__name {
  color: var(--ink-2);
  font-size: var(--text-sm);
  white-space: nowrap;
}

.ws-gauge__bar {
  display: block;
  height: 4px;
  border-radius: var(--radius-pill);
  transition: width var(--dur-number) var(--ease-move);
}

.ws-gauge__bar.is-input {
  background: var(--ink-3);
}

.ws-gauge__bar.is-output {
  background: var(--ink);
}

.ws-gauge__ratio {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}

.ws-gauge__ratio-label {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-gauge__ratio-value {
  font-size: 20px;
  font-weight: 800;
}
</style>
