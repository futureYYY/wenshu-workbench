<script setup lang="ts">
// 文本输入框（06 第 5.2 节）：高 36 px，圆角 8 px，1 px --border-strong；出错时描边变红，下方 12 px 说明；
// 字数限制显示在右下角。class、style 落在外层，其余属性（id、aria-*、data-*）落在 input 上。
import { computed, useAttrs, useTemplateRef } from "vue"

defineOptions({ inheritAttrs: false })

const model = defineModel<string>({ default: "" })

const props = withDefaults(
  defineProps<{
    type?: string
    placeholder?: string
    error?: string | null
    maxlength?: number
    showCount?: boolean
    disabled?: boolean
    readonly?: boolean
    size?: "sm" | "md"
    mono?: boolean
  }>(),
  { type: "text", size: "md" },
)

const emit = defineEmits<{
  enter: [event: KeyboardEvent]
  escape: [event: KeyboardEvent]
  blur: [event: FocusEvent]
  focus: [event: FocusEvent]
}>()

const attrs = useAttrs()
const rootAttrs = computed(() => ({ class: attrs.class, style: attrs.style }))
const inputAttrs = computed(() => {
  const rest: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(attrs)) if (k !== "class" && k !== "style") rest[k] = v
  return rest
})

const input = useTemplateRef<HTMLInputElement>("input")
const length = computed(() => model.value.length)

defineExpose({
  focus: () => input.value?.focus(),
  select: () => input.value?.select(),
  el: input,
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.isComposing) emit("enter", event)
  else if (event.key === "Escape") emit("escape", event)
}
</script>

<template>
  <div
    v-bind="rootAttrs"
    class="ws-input"
    :class="[`ws-input--${props.size}`, { 'is-error': !!error, 'is-disabled': disabled }]"
  >
    <div class="ws-input__box">
      <span v-if="$slots.prefix" class="ws-input__affix"><slot name="prefix" /></span>
      <input
        ref="input"
        v-bind="inputAttrs"
        v-model="model"
        class="ws-input__field"
        :class="{ mono }"
        :type="type"
        :placeholder="placeholder"
        :maxlength="maxlength"
        :disabled="disabled"
        :readonly="readonly"
        :aria-invalid="error ? true : undefined"
        @keydown="onKeydown"
        @blur="emit('blur', $event)"
        @focus="emit('focus', $event)"
      />
      <span v-if="$slots.suffix" class="ws-input__affix"><slot name="suffix" /></span>
    </div>
    <div v-if="error || (showCount && maxlength)" class="ws-input__meta">
      <span v-if="error" class="ws-input__error" role="alert">{{ error }}</span>
      <span v-if="showCount && maxlength" class="ws-input__count num">{{ length }}/{{ maxlength }}</span>
    </div>
  </div>
</template>

<style scoped>
.ws-input {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.ws-input__box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 36px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
  transition: border-color var(--dur-fast) var(--ease-out);
}

.ws-input--sm .ws-input__box {
  height: 28px;
  padding: 0 var(--space-2);
}

.ws-input__box:focus-within {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

.ws-input.is-error .ws-input__box {
  border-color: var(--status-danger);
}

.ws-input.is-disabled .ws-input__box {
  background: var(--surface-2);
  opacity: 0.7;
}

.ws-input__field {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: var(--text-base);
}

.ws-input--sm .ws-input__field {
  font-size: var(--text-sm);
}

.ws-input__field::placeholder {
  color: var(--ink-2);
}

.ws-input__field:focus-visible {
  outline: none;
}

.ws-input__affix {
  display: inline-flex;
  align-items: center;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-input__meta {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: var(--text-xs);
}

.ws-input__error {
  color: var(--status-danger);
}

.ws-input__count {
  margin-left: auto;
  color: var(--ink-2);
}
</style>
