<script setup lang="ts">
// 导视数字：变化时 300 ms 滚动过渡；给了 from 时挂载后从 from 滚到 value。
import { computed } from "vue"
import { useAnimatedNumber } from "@/composables/useAnimatedNumber"
import { DUR } from "@/design/motion"
import { formatNumber } from "@/utils/format"

const props = withDefaults(
  defineProps<{
    value: number
    decimals?: number
    suffix?: string
    format?: (value: number) => string
    from?: number
    delay?: number
  }>(),
  { decimals: 0, delay: 0 },
)

const shown = useAnimatedNumber(() => props.value, DUR.number, props.from, props.delay)

const text = computed(() => {
  if (props.format) return props.format(shown.value)
  if (props.decimals > 0) return `${shown.value.toFixed(props.decimals)}${props.suffix ?? ""}`
  return `${formatNumber(shown.value)}${props.suffix ?? ""}`
})
</script>

<template>
  <span class="num">{{ text }}</span>
</template>
