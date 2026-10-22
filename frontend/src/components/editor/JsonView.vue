<script setup lang="ts">
// 原始输出和解析结果的展示（06 第 5.4 节 JsonView）：格式化缩进，键名 --ink、字符串 --ink-2、数字用导视数字；
// 右上角“复制”，复制后按钮文字变为“已复制” 1.5 秒。不是 JSON 时按纯文本显示。
import { computed, ref } from "vue"
import { copyText } from "@/utils/download"

const props = withDefaults(defineProps<{ value: unknown; raw?: boolean; maxHeight?: string }>(), {
  raw: false,
  maxHeight: "480px",
})

interface Token {
  text: string
  kind: "key" | "string" | "number" | "literal" | "punct" | "plain"
}

const parsed = computed<{ ok: boolean; data: unknown; text: string }>(() => {
  if (typeof props.value === "string") {
    if (props.raw) {
      const trimmed = props.value.trim()
      if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
        try {
          const data = JSON.parse(trimmed) as unknown
          return { ok: true, data, text: JSON.stringify(data, null, 2) }
        } catch {
          return { ok: false, data: null, text: props.value }
        }
      }
    }
    return { ok: false, data: null, text: props.value }
  }
  if (props.value === null || props.value === undefined) return { ok: false, data: null, text: "" }
  try {
    return { ok: true, data: props.value, text: JSON.stringify(props.value, null, 2) }
  } catch {
    return { ok: false, data: null, text: String(props.value) }
  }
})

const TOKEN_RE = /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}[\],])/g

const tokens = computed<Token[]>(() => {
  const text = parsed.value.text
  if (!parsed.value.ok) return [{ text, kind: "plain" }]
  const out: Token[] = []
  let last = 0
  for (const m of text.matchAll(TOKEN_RE)) {
    const index = m.index ?? 0
    if (index > last) out.push({ text: text.slice(last, index), kind: "plain" })
    if (m[1] !== undefined) {
      out.push({ text: m[1], kind: m[2] ? "key" : "string" })
      if (m[2]) out.push({ text: m[2], kind: "punct" })
    } else if (m[3] !== undefined) out.push({ text: m[3], kind: "number" })
    else if (m[4] !== undefined) out.push({ text: m[4], kind: "literal" })
    else out.push({ text: m[0], kind: "punct" })
    last = index + m[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last), kind: "plain" })
  return out
})

const copied = ref(false)
let timer: number | undefined

async function copy() {
  const ok = await copyText(parsed.value.text)
  if (!ok) return
  copied.value = true
  window.clearTimeout(timer)
  timer = window.setTimeout(() => {
    copied.value = false
  }, 1500)
}
</script>

<template>
  <div class="ws-json">
    <button type="button" class="ws-json__copy" :disabled="!parsed.text" @click="copy">
      {{ copied ? "已复制" : "复制" }}
    </button>
    <pre class="ws-json__pre mono" :style="{ maxHeight }"><code><span
      v-for="(t, i) in tokens"
      :key="i"
      :class="`tok-${t.kind}`"
    >{{ t.text }}</span></code></pre>
  </div>
</template>

<style scoped>
.ws-json {
  position: relative;
}

.ws-json__copy {
  position: absolute;
  top: 8px;
  right: 8px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-json__copy:hover:not(:disabled) {
  color: var(--ink);
}

.ws-json__pre {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  padding-right: 72px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--surface-2);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.tok-key {
  color: var(--ink);
  font-weight: 500;
}

.tok-string {
  color: var(--ink-2);
}

.tok-number {
  color: var(--ink);
  font-family: var(--font-num);
  font-variant-numeric: tabular-nums;
}

.tok-literal {
  color: var(--ink);
  font-weight: 500;
}

.tok-punct,
.tok-plain {
  color: var(--ink-2);
}

.ws-json__pre:has(.tok-plain:only-child) .tok-plain {
  color: var(--ink);
}
</style>
