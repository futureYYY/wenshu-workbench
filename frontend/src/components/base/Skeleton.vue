<script setup lang="ts">
// 骨架占位：--surface-2 色块，透明度在 0.6 和 1 之间以 1.2 秒周期变化；减少动态效果时静止。
withDefaults(defineProps<{ width?: string; height?: string; radius?: string }>(), {
  width: "100%",
  height: "14px",
  radius: "4px",
})
</script>

<template>
  <span class="ws-skeleton" aria-hidden="true" :style="{ width, height, borderRadius: radius }" />
</template>

<style scoped>
.ws-skeleton {
  display: block;
  background: var(--surface-2);
  animation: ws-pulse 1.2s ease-in-out infinite;
}
</style>
