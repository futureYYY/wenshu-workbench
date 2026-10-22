<script setup lang="ts">
// 数字输入框：外观同 Input；值为 number | null，失焦时按 min/max 收敛。
import { computed, ref, useAttrs, watch } from "vue"

defineOptions({ inheritAttrs: false })

const model = defineModel<number | null>({ default: null })

const props = withDefaults(
  defineProps<{
    min?: number
    max?: number
    step?: number
    integer?: boolean
    placeholder?: string
    error?: string | null
    disabled?: boolean
    unit?: string
    size?: "sm" | "md"
    width?: number
  }>(),
  { integer: true, size: "md" },
)

const emit = defineEmits<{ enter: [event: KeyboardEvent]; commit: [value: number | null] }>()

const attrs = useAttrs()
const rootAttrs = computed(() => ({ class: attrs.class, style: attrs.style }))
const inputAttrs = computed(() => {
  const rest: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(attrs)) if (k !== "class" && k !== "style") rest[k] = v
  return rest
})

const text = ref(model.value === null || model.value === undefined ? "" : String(model.value))

watch(model, (v) => {
  const current = parse(text.value)
  if (current !== v) text.value = v === null || v === undefined ? "" : String(v)
})

function parse(raw: string): number | null {
  const s = raw.trim().replace(/,/g, "")
  if (!s) return null
  const n = Number(s)
  if (!Number.isFinite(n)) return null
  return props.integer ? Math.trunc(n) : n
}

function clamp(n: number | null): number | null {
  if (n === null) return null
  let v = n
  if (props.min !== undefined) v = Math.max(props.min, v)
  if (props.max !== undefined) v = Math.min(props.max, v)
  return v
}

function onInput(event: Event) {
  text.value = (event.target as HTMLInputElement).value
  const n = parse(text.value)
  model.value = n
}

function commit() {
  const n = clamp(parse(text.value))
  model.value = n
  text.value = n === null ? "" : String(n)
  emit("commit", n)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.isComposing) {
    commit()
    emit("enter", event)
    return
  }
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return
  event.preventDefault()
  const step = (props.step ?? 1) * (event.shiftKey ? 10 : 1)
  const base = parse(text.value) ?? props.min ?? 0
  const next = clamp(base + (event.key === "ArrowUp" ? step : -step))
  model.value = next
  text.value = next === null ? "" : String(next)
}
</script>

<template>
  <div
    v-bind="rootAttrs"
    class="ws-num-input"
    :class="[`ws-num-input--${props.size}`, { 'is-error': !!error, 'is-disabled': disabled }]"
    :style="width ? { width: `${width}px` } : undefined"
  >
    <div class="ws-num-input__box">
      <input
        v-bind="inputAttrs"
        class="ws-num-input__field num"
        type="text"
        inputmode="numeric"
        :value="text"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-invalid="error ? true : undefined"
        @input="onInput"
        @blur="commit"
        @keydown="onKeydown"
      />
      <span v-if="unit" class="ws-num-input__unit">{{ unit }}</span>
    </div>
    <span v-if="error" class="ws-num-input__error" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.ws-num-input {
  display: inline-flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.ws-num-input__box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 36px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
}

.ws-num-input--sm .ws-num-input__box {
  height: 28px;
  padding: 0 var(--space-2);
}

.ws-num-input__box:focus-within {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

.ws-num-input.is-error .ws-num-input__box {
  border-color: var(--status-danger);
}

.ws-num-input.is-disabled .ws-num-input__box {
  background: var(--surface-2);
  opacity: 0.7;
}

.ws-num-input__field {
  flex: 1;
  min-width: 0;
  width: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ink);
  font-size: var(--text-base);
}

.ws-num-input__field::placeholder {
  color: var(--ink-2);
}

.ws-num-input__unit {
  color: var(--ink-2);
  font-size: var(--text-sm);
  white-space: nowrap;
}

.ws-num-input__error {
  color: var(--status-danger);
  font-size: var(--text-xs);
}
</style>
