<script setup lang="ts">
// 提示词编辑器（06 第 5.4 节）：CodeMirror 6，Markdown 模式，自动换行，等宽 13.5 px / 1.7，不显示行号。
// 变量显示为行内小胶囊；未知变量用警告色波浪下划线，悬停提示“未知变量，发送时会原样保留”；
// 输入 {{ 弹出变量补全；高度自适应（最小 160 px，最大视口高度的 60%）；查看历史版本时只读。
import { autocompletion, type Completion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete"
import { markdown } from "@codemirror/lang-markdown"
import { Compartment, EditorState, type Extension } from "@codemirror/state"
import {
  Decoration,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  hoverTooltip,
  placeholder as placeholderExt,
  type DecorationSet,
  type ViewUpdate,
} from "@codemirror/view"
import { minimalSetup } from "codemirror"
import { computed, onBeforeUnmount, onMounted, shallowRef, useId, useTemplateRef, watch } from "vue"
import type { PromptVariable } from "@/api/types"
import { estimateTokens } from "@/utils/text"
import { formatNumber } from "@/utils/format"

type Slot = "system" | "user" | "chunk" | "merge"

const model = defineModel<string>({ default: "" })

const props = withDefaults(
  defineProps<{
    label: string
    /** 这是哪一个模板：决定哪些变量可用 */
    templateSlot: Slot
    variables: PromptVariable[]
    readonly?: boolean
    placeholder?: string
  }>(),
  { readonly: false, placeholder: "" },
)

const host = useTemplateRef<HTMLDivElement>("host")
const view = shallowRef<EditorView | null>(null)
const labelId = useId()

const VAR_RE = /\{\{\s*(col:[^{}]+?|[a-z_]+)\s*\}\}/g

const allowed = computed(() => props.variables.filter((v) => v.templates.includes(props.templateSlot)))
const chips = computed(() => allowed.value.slice(0, 8))

function isKnown(name: string): boolean {
  const n = name.trim()
  if (n.startsWith("col:")) return allowed.value.some((v) => v.name.startsWith("col:"))
  return allowed.value.some((v) => v.name === n)
}

const varMark = Decoration.mark({ class: "cm-ws-var" })
const unknownMark = Decoration.mark({ class: "cm-ws-var cm-ws-var-unknown" })

function variableHighlighter(): Extension {
  const decorator = new MatchDecorator({
    regexp: VAR_RE,
    decoration: (match) => (isKnown(match[1] ?? "") ? varMark : unknownMark),
  })
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet
      constructor(v: EditorView) {
        this.decorations = decorator.createDeco(v)
      }
      update(update: ViewUpdate) {
        this.decorations = decorator.updateDeco(update, this.decorations)
      }
    },
    { decorations: (instance) => instance.decorations },
  )
}

// 未知变量的悬停提示
const unknownTooltip = hoverTooltip((v, pos) => {
  const line = v.state.doc.lineAt(pos)
  const re = new RegExp(VAR_RE.source, "g")
  let m: RegExpExecArray | null
  while ((m = re.exec(line.text)) !== null) {
    const from = line.from + m.index
    const to = from + m[0].length
    if (pos >= from && pos <= to && !isKnown(m[1] ?? "")) {
      return {
        pos: from,
        end: to,
        above: true,
        create: () => {
          const dom = document.createElement("div")
          dom.className = "cm-ws-tip"
          dom.textContent = "未知变量，发送时会原样保留"
          return { dom }
        },
      }
    }
  }
  return null
})

// 输入 {{ 弹出变量补全
function completeVariables(context: CompletionContext): CompletionResult | null {
  const before = context.matchBefore(/\{\{[^{}\s]*$/)
  if (!before) return null
  const options: Completion[] = allowed.value.map((v) => ({
    label: v.insert,
    detail: v.description,
    type: "variable",
    apply: (target: EditorView, _c: Completion, from: number, to: number) => {
      const insert = v.insert
      const cursorOffset = insert.endsWith(":}}") ? insert.length - 2 : insert.length
      target.dispatch({ changes: { from, to, insert }, selection: { anchor: from + cursorOffset } })
    },
  }))
  return { from: before.from, options, validFor: /^\{\{[^{}\s]*$/ }
}

const highlightCompartment = new Compartment()
const readonlyCompartment = new Compartment()

const theme = EditorView.theme({
  "&": {
    fontSize: "13.5px",
    color: "var(--ink)",
    backgroundColor: "var(--surface)",
  },
  "&.cm-focused": {
    outline: "none",
  },
  ".cm-scroller": {
    fontFamily: "var(--font-mono)",
    lineHeight: "1.7",
    minHeight: "160px",
    maxHeight: "60vh",
    overflow: "auto",
  },
  ".cm-content": {
    padding: "10px 12px",
    caretColor: "var(--ink)",
  },
  ".cm-cursor, .cm-dropCursor": {
    borderLeftColor: "var(--ink)",
  },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
    backgroundColor: "var(--surface-3)",
  },
  ".cm-placeholder": {
    color: "var(--ink-2)",
  },
  ".cm-tooltip": {
    border: "1px solid var(--border)",
    backgroundColor: "var(--surface)",
    color: "var(--ink)",
    borderRadius: "10px",
    boxShadow: "var(--float-shadow)",
    overflow: "hidden",
  },
  ".cm-tooltip-autocomplete > ul": {
    fontFamily: "var(--font-mono)",
    maxHeight: "260px",
  },
  ".cm-tooltip-autocomplete > ul > li": {
    padding: "4px 10px",
  },
  ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
    backgroundColor: "var(--surface-2)",
    color: "var(--ink)",
  },
  ".cm-completionDetail": {
    marginLeft: "10px",
    color: "var(--ink-2)",
    fontFamily: "var(--font-sans)",
    fontStyle: "normal",
  },
})

function build(doc: string): EditorState {
  return EditorState.create({
    doc,
    extensions: [
      minimalSetup,
      markdown(),
      EditorView.lineWrapping,
      theme,
      placeholderExt(props.placeholder),
      highlightCompartment.of(variableHighlighter()),
      readonlyCompartment.of([EditorState.readOnly.of(props.readonly), EditorView.editable.of(!props.readonly)]),
      unknownTooltip,
      autocompletion({ override: [completeVariables], activateOnTyping: true, icons: false }),
      EditorView.contentAttributes.of({ "aria-labelledby": labelId, "aria-multiline": "true" }),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          const text = update.state.doc.toString()
          if (text !== model.value) model.value = text
        }
      }),
    ],
  })
}

onMounted(() => {
  if (!host.value) return
  view.value = new EditorView({ state: build(model.value), parent: host.value })
})

onBeforeUnmount(() => {
  view.value?.destroy()
  view.value = null
})

// 外部改了内容（切换模板、恢复草稿、恢复版本）时同步到编辑器
watch(model, (text) => {
  const v = view.value
  if (!v) return
  const current = v.state.doc.toString()
  if (text !== current) v.dispatch({ changes: { from: 0, to: current.length, insert: text } })
})

watch([allowed, () => props.templateSlot], () => {
  view.value?.dispatch({ effects: highlightCompartment.reconfigure(variableHighlighter()) })
})

watch(
  () => props.readonly,
  (ro) => {
    view.value?.dispatch({
      effects: readonlyCompartment.reconfigure([EditorState.readOnly.of(ro), EditorView.editable.of(!ro)]),
    })
  },
)

function insertVariable(v: PromptVariable) {
  const ed = view.value
  if (!ed || props.readonly) return
  const { from, to } = ed.state.selection.main
  const insert = v.insert
  const cursorOffset = insert.endsWith(":}}") ? insert.length - 2 : insert.length
  ed.dispatch({ changes: { from, to, insert }, selection: { anchor: from + cursorOffset } })
  ed.focus()
}

function focus() {
  view.value?.focus()
}

defineExpose({ focus })

const charCount = computed(() => model.value.length)
const tokenCount = computed(() => estimateTokens(model.value))
</script>

<template>
  <div class="ws-editor" :class="{ 'is-readonly': readonly }">
    <div class="ws-editor__bar">
      <span :id="labelId" class="ws-editor__label">{{ label }}</span>
      <span v-if="!readonly" class="ws-editor__chips">
        <button
          v-for="v in chips"
          :key="v.name"
          type="button"
          class="ws-editor__chip mono"
          :title="v.description"
          @click="insertVariable(v)"
        >
          {{ v.insert }}
        </button>
      </span>
      <span class="ws-editor__count">
        <span class="num">{{ formatNumber(charCount) }}</span> 字 约 <span class="num">{{ formatNumber(tokenCount) }}</span>
      </span>
    </div>
    <div ref="host" class="ws-editor__host" />
  </div>
</template>

<style scoped>
.ws-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-editor__bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 24px;
}

.ws-editor__label {
  flex-shrink: 0;
  font-size: var(--text-sm);
  font-weight: 500;
}

.ws-editor__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.ws-editor__chip {
  height: 22px;
  padding: 0 6px;
  border: 0;
  border-radius: 4px;
  background: color-mix(in srgb, var(--line-0) 12%, transparent);
  color: var(--status-running);
  font-size: var(--text-xs);
}

.ws-editor__chip:hover {
  background: color-mix(in srgb, var(--line-0) 20%, transparent);
}

.ws-editor__count {
  flex-shrink: 0;
  margin-left: auto;
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-editor__host {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  overflow: hidden;
}

.ws-editor__host:focus-within {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

.ws-editor.is-readonly .ws-editor__host {
  background: var(--surface-2);
}

/* 变量胶囊：线路色 0 的 12% 作底色，文字用同色系、对比度更高的 --status-running（06 第 5.4 节） */
.ws-editor__host :deep(.cm-ws-var) {
  padding: 1px 0;
  border-radius: 4px;
  background: color-mix(in srgb, var(--line-0) 12%, transparent);
  color: var(--status-running);
}

.ws-editor__host :deep(.cm-ws-var-unknown) {
  background: transparent;
  color: var(--status-warn);
  text-decoration: underline wavy var(--status-warn);
  text-underline-offset: 3px;
}

.ws-editor__host :deep(.cm-ws-tip) {
  padding: 6px 10px;
  font-family: var(--font-sans);
  font-size: var(--text-xs);
}
</style>
