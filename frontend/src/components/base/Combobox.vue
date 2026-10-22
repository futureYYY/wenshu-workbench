<script setup lang="ts">
// 可输入的下拉（模型名：获取列表成功后可搜索选择，也允许手填）。
// 自绘：输入框 + 过滤后的列表，↑↓ 选择，Enter 确认，Esc 关闭。
import { computed, nextTick, ref, useId, useTemplateRef, watch } from "vue"

const model = defineModel<string>({ default: "" })

const props = withDefaults(
  defineProps<{
    options: string[]
    placeholder?: string
    error?: string | null
    disabled?: boolean
    mono?: boolean
    emptyText?: string
  }>(),
  { emptyText: "没有匹配的模型，可以直接填写" },
)

const open = ref(false)
const active = ref(-1)
const listId = useId()
const input = useTemplateRef<HTMLInputElement>("input")
const list = useTemplateRef<HTMLUListElement>("list")

const filtered = computed(() => {
  const q = model.value.trim().toLowerCase()
  const all = props.options
  if (!q) return all.slice(0, 200)
  return all.filter((o) => o.toLowerCase().includes(q)).slice(0, 200)
})

watch(filtered, () => {
  active.value = filtered.value.length ? 0 : -1
})

function show() {
  if (props.disabled || props.options.length === 0) return
  open.value = true
  active.value = Math.max(0, filtered.value.indexOf(model.value))
}

function choose(value: string) {
  model.value = value
  open.value = false
  void nextTick(() => input.value?.focus())
}

function scrollActive() {
  void nextTick(() => {
    const el = list.value?.querySelector<HTMLElement>(`[data-index="${active.value}"]`)
    el?.scrollIntoView({ block: "nearest" })
  })
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown") {
    event.preventDefault()
    if (!open.value) return show()
    active.value = Math.min(filtered.value.length - 1, active.value + 1)
    scrollActive()
  } else if (event.key === "ArrowUp") {
    event.preventDefault()
    active.value = Math.max(0, active.value - 1)
    scrollActive()
  } else if (event.key === "Enter" && open.value) {
    const value = filtered.value[active.value]
    if (value !== undefined) {
      event.preventDefault()
      choose(value)
    }
  } else if (event.key === "Escape" && open.value) {
    event.preventDefault()
    event.stopPropagation()
    open.value = false
  }
}

function onBlur() {
  // 让列表项的点击先生效
  window.setTimeout(() => {
    open.value = false
  }, 120)
}
</script>

<template>
  <div class="ws-combo" :class="{ 'is-error': !!error }">
    <div class="ws-combo__box">
      <input
        ref="input"
        v-model="model"
        class="ws-combo__field"
        :class="{ mono }"
        role="combobox"
        :aria-expanded="open"
        :aria-controls="listId"
        aria-autocomplete="list"
        :aria-activedescendant="open && active >= 0 ? `${listId}-${active}` : undefined"
        :placeholder="placeholder"
        :disabled="disabled"
        @focus="show"
        @input="show"
        @keydown="onKeydown"
        @blur="onBlur"
      />
      <slot name="suffix" />
    </div>
    <ul v-if="open" :id="listId" ref="list" class="ws-combo__list" role="listbox">
      <li
        v-for="(opt, i) in filtered"
        :id="`${listId}-${i}`"
        :key="opt"
        :data-index="i"
        role="option"
        class="ws-combo__option"
        :class="{ 'is-active': i === active, 'is-selected': opt === model }"
        :aria-selected="opt === model"
        @mousedown.prevent="choose(opt)"
        @mouseenter="active = i"
      >
        {{ opt }}
      </li>
      <li v-if="filtered.length === 0" class="ws-combo__empty">{{ emptyText }}</li>
    </ul>
    <span v-if="error" class="ws-combo__error" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.ws-combo {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}

.ws-combo__box {
  display: flex;
  align-items: center;
  height: 36px;
  padding: 0 var(--space-1) 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
}

.ws-combo__box:focus-within {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

.ws-combo.is-error .ws-combo__box {
  border-color: var(--status-danger);
}

.ws-combo__field {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ink);
  font-size: var(--text-base);
}

.ws-combo__field.mono {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.ws-combo__field::placeholder {
  color: var(--ink-2);
}

.ws-combo__list {
  position: absolute;
  top: 42px;
  left: 0;
  right: 0;
  z-index: var(--z-dropdown);
  max-height: 280px;
  margin: 0;
  padding: var(--space-1);
  overflow-y: auto;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-popover);
  background: var(--surface);
  box-shadow: var(--float-shadow);
  animation: ws-pop-in var(--dur-fast) var(--ease-out);
}

.ws-combo__option {
  position: relative;
  min-height: 32px;
  padding: 6px var(--space-3) 6px var(--space-4);
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  cursor: pointer;
}

.ws-combo__option.is-active {
  background: var(--surface-2);
}

.ws-combo__option.is-selected::before {
  content: "";
  position: absolute;
  left: 4px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--ink);
}

.ws-combo__empty {
  padding: var(--space-2) var(--space-3);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-combo__error {
  color: var(--status-danger);
  font-size: var(--text-xs);
}
</style>
