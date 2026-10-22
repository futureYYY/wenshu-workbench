<script setup lang="ts">
// 多行输入框：与 Input 同一套外观；Ctrl+Enter 触发 submit。
import { computed, useAttrs, useTemplateRef } from "vue"

defineOptions({ inheritAttrs: false })

const model = defineModel<string>({ default: "" })

withDefaults(
  defineProps<{
    placeholder?: string
    error?: string | null
    maxlength?: number
    showCount?: boolean
    rows?: number
    disabled?: boolean
    readonly?: boolean
    mono?: boolean
    resize?: boolean
  }>(),
  { rows: 6, resize: true },
)

const emit = defineEmits<{ submit: [event: KeyboardEvent] }>()

const attrs = useAttrs()
const rootAttrs = computed(() => ({ class: attrs.class, style: attrs.style }))
const fieldAttrs = computed(() => {
  const rest: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(attrs)) if (k !== "class" && k !== "style") rest[k] = v
  return rest
})

const field = useTemplateRef<HTMLTextAreaElement>("field")
defineExpose({ focus: () => field.value?.focus(), el: field })

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    emit("submit", event)
  }
}
</script>

<template>
  <div v-bind="rootAttrs" class="ws-textarea" :class="{ 'is-error': !!error }">
    <textarea
      ref="field"
      v-bind="fieldAttrs"
      v-model="model"
      class="ws-textarea__field"
      :class="{ mono, 'no-resize': !resize }"
      :rows="rows"
      :placeholder="placeholder"
      :maxlength="maxlength"
      :disabled="disabled"
      :readonly="readonly"
      :aria-invalid="error ? true : undefined"
      @keydown="onKeydown"
    />
    <div v-if="error || (showCount && maxlength)" class="ws-textarea__meta">
      <span v-if="error" class="ws-textarea__error" role="alert">{{ error }}</span>
      <span v-if="showCount && maxlength" class="ws-textarea__count num">{{ model.length }}/{{ maxlength }}</span>
    </div>
  </div>
</template>

<style scoped>
.ws-textarea {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ws-textarea__field {
  width: 100%;
  min-height: 72px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-size: var(--text-base);
  line-height: 1.7;
  resize: vertical;
}

.ws-textarea__field.no-resize {
  resize: none;
}

.ws-textarea__field.mono {
  font-family: var(--font-mono);
  font-size: 13.5px;
}

.ws-textarea__field::placeholder {
  color: var(--ink-2);
}

.ws-textarea.is-error .ws-textarea__field {
  border-color: var(--status-danger);
}

.ws-textarea__meta {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
}

.ws-textarea__error {
  color: var(--status-danger);
}

.ws-textarea__count {
  margin-left: auto;
  color: var(--ink-2);
}
</style>
