<script setup lang="ts">
// Logo 符号（06 第 2 节）：枢纽胶囊左侧接入一段墨色短线，右侧分出蓝、绿两段线路，表示“一进多出”。
// 几何与 public/favicon.svg、packaging/icon.svg 相同，颜色走令牌。
withDefaults(defineProps<{ size?: number; label?: string }>(), { size: 28 })
</script>

<template>
  <svg
    class="ws-logo"
    :width="size"
    :height="size"
    viewBox="0 0 48 48"
    fill="none"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
  >
    <path d="M3 24H11" class="ws-logo__ink" stroke-width="3.5" stroke-linecap="round" />
    <path
      d="M35 21.5L39.5 17H45"
      class="ws-logo__a"
      stroke-width="3.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <path
      d="M35 26.5L39.5 31H45"
      class="ws-logo__b"
      stroke-width="3.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <rect x="11" y="17" width="24" height="14" rx="7" class="ws-logo__hub" stroke-width="2.5" />
  </svg>
</template>

<style scoped>
.ws-logo__ink {
  stroke: var(--ink);
}

.ws-logo__a {
  stroke: var(--line-0);
}

.ws-logo__b {
  stroke: var(--line-1);
}

.ws-logo__hub {
  fill: var(--surface);
  stroke: var(--ink);
}
</style>
