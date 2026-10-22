<script setup lang="ts">
// 接入模型 / 编辑模型（06 第 6.8 节）：宽 720 px 的抽屉表单。
// 输入地址时实时显示“实际请求”，粘贴了 /chat/completions 时自动去掉并提示；
// “获取列表”成功后模型名变成可搜索的下拉；“测试连接”用表单当前内容测试，不需要先保存。
// API Key（04 第 4 节）：密钥框没动过就不带 api_key；输入了新值才带上；“清除密钥”保存时发送 api_key: null。
import { CircleCheck, CircleX, Eye, EyeOff, Plus, Trash2 } from "@lucide/vue"
import { computed, ref, watch } from "vue"
import { ApiError, modelsApi } from "@/api/endpoints"
import type { ModelConfig, ModelConfigInput, ModelConfigPatch, ModelTestResult } from "@/api/types"
import Button from "@/components/base/Button.vue"
import Collapsible from "@/components/base/Collapsible.vue"
import Combobox from "@/components/base/Combobox.vue"
import Drawer from "@/components/base/Drawer.vue"
import FieldRow from "@/components/base/FieldRow.vue"
import IconButton from "@/components/base/IconButton.vue"
import Input from "@/components/base/Input.vue"
import NumberInput from "@/components/base/NumberInput.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Slider from "@/components/base/Slider.vue"
import Switch from "@/components/base/Switch.vue"
import Textarea from "@/components/base/Textarea.vue"
import { isPlaceholderModel } from "@/stores/models"
import { formatDurationMs } from "@/utils/format"
import { clip } from "@/utils/text"
import { notify, notifyError } from "@/utils/toast"

const open = defineModel<boolean>("open", { default: false })
const props = defineProps<{ model: ModelConfig | null }>()
const emit = defineEmits<{ saved: [model: ModelConfig, created: boolean] }>()

const CONTEXT_PRESETS: { value: string; label: string; tokens: number }[] = [
  { value: "8192", label: "8K", tokens: 8192 },
  { value: "32768", label: "32K", tokens: 32768 },
  { value: "65536", label: "64K", tokens: 65536 },
  { value: "131072", label: "128K", tokens: 131072 },
]

interface HeaderRow {
  name: string
  value: string
}

interface FormState {
  name: string
  base_url: string
  api_key: string
  model: string
  temperature: number
  max_output_tokens: number | null
  max_tokens_param: "max_tokens" | "max_completion_tokens"
  context_window: number | null
  context_preset: string
  timeout_s: number | null
  concurrency_cap: number | null
  json_mode: boolean
  verify_ssl: boolean
  proxy_url: string
  headers: HeaderRow[]
  extra_body_text: string
}

const form = ref<FormState>(emptyForm())
const errors = ref<Record<string, string>>({})
const showKey = ref(false)
/** 已保存的密钥被标记为“待清除”：保存时发送 api_key: null */
const clearKey = ref(false)
const advancedOpen = ref(false)
const stripHint = ref(false)
const remoteModels = ref<string[]>([])
const listing = ref(false)
const listHint = ref<string | null>(null)
const testing = ref(false)
const testResult = ref<ModelTestResult | null>(null)
const saving = ref(false)

const isEdit = computed(() => props.model !== null)
const isDemo = computed(() => props.model?.provider_kind === "demo")

function emptyForm(): FormState {
  return {
    name: "",
    base_url: "",
    api_key: "",
    model: "",
    temperature: 0.3,
    max_output_tokens: 1024,
    max_tokens_param: "max_tokens",
    context_window: 32768,
    context_preset: "32768",
    timeout_s: 120,
    concurrency_cap: 20,
    json_mode: false,
    verify_ssl: true,
    proxy_url: "",
    headers: [],
    extra_body_text: "{}",
  }
}

function fromModel(m: ModelConfig): FormState {
  const preset = CONTEXT_PRESETS.find((p) => p.tokens === m.context_window)
  return {
    name: m.name,
    base_url: m.provider_kind === "demo" ? "" : isPlaceholderModel(m) ? "" : m.base_url,
    api_key: "",
    model: isPlaceholderModel(m) ? "" : m.model,
    temperature: m.temperature,
    max_output_tokens: m.max_output_tokens,
    max_tokens_param: m.max_tokens_param,
    context_window: m.context_window,
    context_preset: preset ? preset.value : "custom",
    timeout_s: m.timeout_s,
    concurrency_cap: m.concurrency_cap,
    json_mode: m.json_mode,
    verify_ssl: m.verify_ssl,
    proxy_url: m.proxy_url ?? "",
    headers: Object.entries(m.extra_headers).map(([name, value]) => ({ name, value })),
    extra_body_text: JSON.stringify(m.extra_body, null, 2),
  }
}

watch(
  () => [open.value, props.model?.id],
  () => {
    if (!open.value) return
    form.value = props.model ? fromModel(props.model) : emptyForm()
    errors.value = {}
    testResult.value = null
    remoteModels.value = []
    listHint.value = null
    stripHint.value = false
    showKey.value = false
    clearKey.value = false
    advancedOpen.value = false
  },
  { immediate: true },
)

// 输入了新密钥就不再清除：保存时直接替换
watch(
  () => form.value.api_key,
  (value) => {
    if (value.trim()) clearKey.value = false
  },
)

function toggleClearKey() {
  clearKey.value = !clearKey.value
  if (clearKey.value) form.value.api_key = ""
}

// ---- 地址：实时显示实际请求；粘贴 /chat/completions 自动去掉 ----
function normalizeBaseUrl(raw: string): string {
  let url = raw.trim().replace(/\/+$/, "")
  if (/\/chat\/completions$/i.test(url)) url = url.replace(/\/chat\/completions$/i, "").replace(/\/+$/, "")
  return url
}

watch(
  () => form.value.base_url,
  (value) => {
    if (/\/chat\/completions\/?\s*$/i.test(value)) {
      form.value.base_url = normalizeBaseUrl(value)
      stripHint.value = true
    }
  },
)

const requestUrl = computed(() => {
  if (isDemo.value) return "本机模拟"
  const base = normalizeBaseUrl(form.value.base_url)
  return base ? `${base}/chat/completions` : ""
})

const contextModel = computed({
  get: () => form.value.context_preset,
  set: (value: string) => {
    form.value.context_preset = value
    const preset = CONTEXT_PRESETS.find((p) => p.value === value)
    if (preset) form.value.context_window = preset.tokens
  },
})

const maxParamModel = computed({
  get: () => form.value.max_tokens_param as string,
  set: (value: string) => {
    form.value.max_tokens_param = value === "max_completion_tokens" ? "max_completion_tokens" : "max_tokens"
  },
})

// ---- 额外请求体：失焦时校验，格式错误时标出位置 ----
function parseExtraBody(): Record<string, unknown> | null {
  const text = form.value.extra_body_text.trim()
  if (!text) return {}
  try {
    const value = JSON.parse(text) as unknown
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      errors.value = { ...errors.value, extra_body: "需要一个 JSON 对象，例如 { \"enable_thinking\": false }" }
      return null
    }
    const next = { ...errors.value }
    delete next.extra_body
    errors.value = next
    return value as Record<string, unknown>
  } catch (e) {
    const m = /position (\d+)/i.exec(String(e))
    errors.value = {
      ...errors.value,
      extra_body: m ? `不是有效的 JSON：第 ${Number(m[1]) + 1} 个字符附近有错误` : "不是有效的 JSON",
    }
    return null
  }
}

function headersObject(): Record<string, string> {
  const out: Record<string, string> = {}
  for (const row of form.value.headers) {
    const name = row.name.trim()
    if (name) out[name] = row.value
  }
  return out
}

function addHeader() {
  form.value.headers.push({ name: "", value: "" })
}

function removeHeader(index: number) {
  form.value.headers.splice(index, 1)
}

// ---- 组装请求体 ----
function buildInput(): ModelConfigInput | null {
  const extra = parseExtraBody()
  if (extra === null) return null
  const f = form.value
  const input: ModelConfigInput = {
    name: f.name.trim(),
    base_url: normalizeBaseUrl(f.base_url),
    model: f.model.trim(),
    temperature: f.temperature,
    max_output_tokens: f.max_output_tokens ?? 1024,
    max_tokens_param: f.max_tokens_param,
    context_window: f.context_window ?? 32768,
    timeout_s: f.timeout_s ?? 120,
    concurrency_cap: f.concurrency_cap ?? 20,
    json_mode: f.json_mode,
    verify_ssl: f.verify_ssl,
    proxy_url: f.proxy_url.trim() || null,
    extra_headers: headersObject(),
    extra_body: extra,
  }
  // 密钥框没动过：不带 api_key（编辑时保留已保存的密钥，测试和获取列表也用它）；标记了清除：null
  const key = f.api_key.trim()
  if (key) input.api_key = key
  else if (clearKey.value) input.api_key = null
  return input
}

function validateLocal(): boolean {
  const next: Record<string, string> = {}
  const f = form.value
  if (!f.name.trim()) next.name = "不能为空"
  if (!isDemo.value) {
    const base = normalizeBaseUrl(f.base_url)
    if (!/^https?:\/\//i.test(base)) next.base_url = "必须以 http:// 或 https:// 开头"
    if (!f.model.trim()) next.model = "不能为空"
    const proxy = f.proxy_url.trim()
    if (proxy && !/^https?:\/\//i.test(proxy)) {
      next.proxy_url = "代理地址必须以 http:// 或 https:// 开头"
      advancedOpen.value = true
    }
  }
  errors.value = { ...next, ...(errors.value.extra_body ? { extra_body: errors.value.extra_body } : {}) }
  return Object.keys(next).length === 0
}

function applyServerErrors(e: unknown) {
  if (!(e instanceof ApiError)) return
  if (e.code === "MODEL_NAME_TAKEN") {
    errors.value = { ...errors.value, name: e.message }
    return
  }
  const next = { ...errors.value }
  for (const f of e.fields) {
    const key = f.path.replace(/^config\./, "").split(".")[0] ?? f.path
    next[key] = f.message
  }
  errors.value = next
}

/** 编辑时只发送改动过的字段 */
function buildPatch(original: ModelConfig, input: ModelConfigInput): ModelConfigPatch {
  const patch: ModelConfigPatch = {}
  if (isDemo.value) {
    if (input.name !== original.name) patch.name = input.name
    if (input.temperature !== original.temperature) patch.temperature = input.temperature
    if (input.max_output_tokens !== original.max_output_tokens) patch.max_output_tokens = input.max_output_tokens
    if (input.context_window !== original.context_window) patch.context_window = input.context_window
    if (input.concurrency_cap !== original.concurrency_cap) patch.concurrency_cap = input.concurrency_cap
    return patch
  }
  if (input.name !== original.name) patch.name = input.name
  if (input.base_url !== original.base_url) patch.base_url = input.base_url
  if (input.model !== original.model) patch.model = input.model
  if (input.api_key !== undefined) patch.api_key = input.api_key
  if (input.temperature !== original.temperature) patch.temperature = input.temperature
  if (input.max_output_tokens !== original.max_output_tokens) patch.max_output_tokens = input.max_output_tokens
  if (input.max_tokens_param !== original.max_tokens_param) patch.max_tokens_param = input.max_tokens_param
  if (input.context_window !== original.context_window) patch.context_window = input.context_window
  if (input.timeout_s !== original.timeout_s) patch.timeout_s = input.timeout_s
  if (input.concurrency_cap !== original.concurrency_cap) patch.concurrency_cap = input.concurrency_cap
  if (input.json_mode !== original.json_mode) patch.json_mode = input.json_mode
  if (input.verify_ssl !== original.verify_ssl) patch.verify_ssl = input.verify_ssl
  if ((input.proxy_url ?? null) !== original.proxy_url) patch.proxy_url = input.proxy_url ?? null
  if (JSON.stringify(input.extra_headers) !== JSON.stringify(original.extra_headers)) patch.extra_headers = input.extra_headers
  if (JSON.stringify(input.extra_body) !== JSON.stringify(original.extra_body)) patch.extra_body = input.extra_body
  return patch
}

async function save() {
  if (saving.value || !validateLocal()) return
  const input = buildInput()
  if (!input) return
  saving.value = true
  try {
    const original = props.model
    if (original) {
      const patch = buildPatch(original, input)
      const next = Object.keys(patch).length ? await modelsApi.update(original.id, patch) : original
      notify("已保存")
      emit("saved", next, false)
    } else {
      const next = await modelsApi.create(input)
      notify("已保存")
      emit("saved", next, true)
    }
    open.value = false
  } catch (e) {
    applyServerErrors(e)
    notifyError(e)
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  if (testing.value) return
  testResult.value = null
  if (isDemo.value && props.model) {
    testing.value = true
    try {
      testResult.value = await modelsApi.test(props.model.id)
    } catch (e) {
      notifyError(e)
    } finally {
      testing.value = false
    }
    return
  }
  if (!validateLocal()) return
  const input = buildInput()
  if (!input) return
  testing.value = true
  try {
    testResult.value = await modelsApi.testDraft({ config: input, model_id: props.model?.id ?? null })
  } catch (e) {
    applyServerErrors(e)
    notifyError(e)
  } finally {
    testing.value = false
  }
}

async function fetchList() {
  const base = normalizeBaseUrl(form.value.base_url)
  if (!/^https?:\/\//i.test(base)) {
    errors.value = { ...errors.value, base_url: "必须以 http:// 或 https:// 开头" }
    return
  }
  const input = buildInput()
  if (!input) return
  listing.value = true
  listHint.value = null
  try {
    // 模型名还没填时也能获取列表
    const models = await modelsApi.listRemote({
      config: { ...input, name: input.name || "临时", model: input.model || "placeholder" },
      model_id: props.model?.id ?? null,
    })
    remoteModels.value = models
    listHint.value = models.length ? `获取到 ${models.length} 个模型，可以搜索选择` : "这个接口没有返回模型，请手动填写模型名"
  } catch (e) {
    remoteModels.value = []
    listHint.value =
      e instanceof ApiError && e.code === "UPSTREAM_ERROR" ? e.message || "这个接口不支持获取模型列表，请手动填写模型名" : "这个接口不支持获取模型列表，请手动填写模型名"
  } finally {
    listing.value = false
  }
}

const title = computed(() => (isEdit.value ? "编辑模型" : "接入模型"))
const hasSavedKey = computed(() => !!props.model?.has_api_key)
const keyPlaceholder = computed(() => {
  const m = props.model
  if (!m || !m.has_api_key) return "sk-…"
  if (clearKey.value) return "保存后清除已保存的密钥"
  return `已保存（${m.api_key_masked ?? "…"}），不修改请留空`
})
const keyHint = computed(() => {
  if (hasSavedKey.value) return clearKey.value ? "保存后会清除已保存的密钥；也可以输入新的密钥替换它" : ""
  return isEdit.value ? "还没有保存密钥。本机 Ollama、vLLM 可以不填" : "本机 Ollama、vLLM 可以不填"
})
const placeholderNotice = computed(() => (props.model && isPlaceholderModel(props.model) ? "这是首次启动生成的占位条目：填写真实的接口地址、API Key 和模型名，保存后会自动启用。" : null))
</script>

<template>
  <Drawer v-model:open="open" :width="720" :title="title">
    <form class="ws-mform" novalidate @submit.prevent="save">
      <p v-if="placeholderNotice" class="ws-mform__notice">{{ placeholderNotice }}</p>

      <FieldRow label="名称" for="mf-name">
        <Input id="mf-name" v-model="form.name" :maxlength="40" :error="errors.name" placeholder="例如 DeepSeek" />
      </FieldRow>

      <FieldRow v-if="!isDemo" label="接口地址" for="mf-base" align="start">
        <Input
          id="mf-base"
          v-model="form.base_url"
          :error="errors.base_url"
          placeholder="例如 https://api.deepseek.com/v1"
          mono
          spellcheck="false"
        />
        <template #hint>
          <span v-if="requestUrl">实际请求：<span class="mono">{{ requestUrl }}</span></span>
          <span v-if="stripHint" class="ws-mform__ok">已去掉末尾的 /chat/completions</span>
        </template>
      </FieldRow>
      <FieldRow v-else label="接口地址">
        <span class="ws-mform__muted">本机模拟，不需要密钥，不消耗额度</span>
      </FieldRow>

      <FieldRow v-if="!isDemo" label="API Key" for="mf-key">
        <Input
          id="mf-key"
          v-model="form.api_key"
          :type="showKey ? 'text' : 'password'"
          autocomplete="off"
          spellcheck="false"
          mono
          :placeholder="keyPlaceholder"
        >
          <template #suffix>
            <button type="button" class="ws-mform__eye" :aria-label="showKey ? '隐藏' : '显示'" @click="showKey = !showKey">
              <EyeOff v-if="showKey" :size="16" :stroke-width="1.75" aria-hidden="true" />
              <Eye v-else :size="16" :stroke-width="1.75" aria-hidden="true" />
              <span>{{ showKey ? "隐藏" : "显示" }}</span>
            </button>
          </template>
        </Input>
        <template v-if="keyHint || hasSavedKey" #hint>
          <span class="ws-mform__key-hint">
            <span :class="{ 'ws-mform__warn': clearKey }">{{ keyHint }}</span>
            <Button v-if="hasSavedKey" variant="text" size="sm" data-testid="clear-api-key" @click="toggleClearKey">
              {{ clearKey ? "撤销清除" : "清除密钥" }}
            </Button>
          </span>
        </template>
      </FieldRow>

      <FieldRow v-if="!isDemo" label="模型名" for="mf-model" align="start">
        <div class="ws-mform__inline">
          <Combobox id="mf-model" v-model="form.model" :options="remoteModels" :error="errors.model" mono placeholder="例如 deepseek-chat" />
          <Button variant="secondary" :loading="listing" @click="fetchList">获取列表</Button>
        </div>
        <template v-if="listHint" #hint>{{ listHint }}</template>
      </FieldRow>

      <div class="ws-mform__divider"><span>常用参数</span></div>

      <FieldRow label="温度">
        <div class="ws-mform__slider">
          <Slider v-model="form.temperature" :min="0" :max="2" :step="0.1" :ticks="[0, 0.5, 1, 1.5, 2]" aria-label="温度" />
          <span class="num ws-mform__value">{{ form.temperature.toFixed(1) }}</span>
        </div>
      </FieldRow>

      <FieldRow label="最大输出">
        <NumberInput v-model="form.max_output_tokens" :min="16" :max="32768" :width="140" unit="tokens" aria-label="最大输出" />
      </FieldRow>

      <FieldRow label="上下文长度" align="start">
        <div class="ws-mform__inline">
          <SegmentedControl
            v-model="contextModel"
            size="sm"
            aria-label="上下文长度"
            :options="[...CONTEXT_PRESETS.map((p) => ({ value: p.value, label: p.label })), { value: 'custom', label: '自定义' }]"
          />
          <NumberInput
            v-if="form.context_preset === 'custom'"
            v-model="form.context_window"
            :min="1024"
            :max="2000000"
            :width="140"
            unit="tokens"
            aria-label="自定义上下文长度"
          />
        </div>
      </FieldRow>

      <FieldRow v-if="!isDemo" label="超时">
        <NumberInput v-model="form.timeout_s" :min="5" :max="600" :width="120" unit="秒" aria-label="超时" />
      </FieldRow>

      <FieldRow label="并发上限" hint="多个任务共用这个模型时，同时请求的总数不超过它">
        <NumberInput v-model="form.concurrency_cap" :min="1" :max="20" :width="100" aria-label="并发上限" />
      </FieldRow>

      <Collapsible v-if="!isDemo" v-model:open="advancedOpen" title="高级">
        <div class="ws-mform__advanced">
          <FieldRow label="最大输出参数名">
            <SegmentedControl
              v-model="maxParamModel"
              size="sm"
              aria-label="最大输出参数名"
              :options="[
                { value: 'max_tokens', label: 'max_tokens' },
                { value: 'max_completion_tokens', label: 'max_completion_tokens' },
              ]"
            />
          </FieldRow>
          <FieldRow label="JSON 输出模式" hint="接口支持 response_format 时再打开">
            <Switch v-model="form.json_mode" aria-label="JSON 输出模式" />
          </FieldRow>
          <FieldRow label="校验证书" hint="公司内网用自签名证书时关闭">
            <Switch v-model="form.verify_ssl" aria-label="校验证书" />
          </FieldRow>
          <FieldRow label="代理" for="mf-proxy">
            <Input
              id="mf-proxy"
              v-model="form.proxy_url"
              mono
              placeholder="留空表示直连，例如 http://127.0.0.1:7890"
              :error="errors.proxy_url"
            />
          </FieldRow>
          <FieldRow label="自定义请求头" align="start">
            <div class="ws-mform__headers">
              <div v-for="(row, i) in form.headers" :key="i" class="ws-mform__header-row">
                <Input v-model="row.name" mono size="sm" placeholder="名称" :aria-label="`请求头 ${i + 1} 的名称`" />
                <Input v-model="row.value" mono size="sm" placeholder="值" :aria-label="`请求头 ${i + 1} 的值`" />
                <IconButton label="删除这个请求头" size="sm" @click="removeHeader(i)"><Trash2 :size="14" :stroke-width="1.75" /></IconButton>
              </div>
              <Button variant="text" size="sm" @click="addHeader">
                <template #icon><Plus :size="14" :stroke-width="1.75" /></template>
                添加
              </Button>
              <p v-if="errors.extra_headers" class="ws-mform__error">{{ errors.extra_headers }}</p>
            </div>
          </FieldRow>
          <FieldRow label="额外请求体" align="start" hint="值为 null 表示不发送该参数">
            <Textarea
              v-model="form.extra_body_text"
              :rows="4"
              mono
              :error="errors.extra_body"
              aria-label="额外请求体（JSON）"
              @blur="parseExtraBody"
            />
          </FieldRow>
        </div>
      </Collapsible>
    </form>

    <template #footer>
      <div class="ws-mform__result" aria-live="polite">
        <template v-if="testing">
          <span class="ws-mform__muted">测试中</span>
          <span class="ws-mform__shuttle" aria-hidden="true"><span class="ws-shuttle" /></span>
        </template>
        <template v-else-if="testResult">
          <span v-if="testResult.ok" class="ws-mform__ok">
            <CircleCheck :size="16" :stroke-width="2" aria-hidden="true" />{{ testResult.message }}
          </span>
          <span v-else class="ws-mform__fail">
            <CircleX :size="16" :stroke-width="2" aria-hidden="true" />{{ testResult.message }}
          </span>
          <span v-if="testResult.latency_ms !== null" class="ws-mform__muted">{{ formatDurationMs(testResult.latency_ms) }}</span>
          <span v-if="testResult.ok && testResult.sample_output" class="ws-mform__muted">返回“{{ clip(testResult.sample_output, 20) }}”</span>
        </template>
      </div>
      <Button variant="secondary" :loading="testing" @click="testConnection">测试连接</Button>
      <Button variant="primary" :loading="saving" data-testid="save-model" @click="save">保存</Button>
    </template>
  </Drawer>
</template>

<style scoped>
.ws-mform {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-mform__notice {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-control);
  background: var(--surface-2);
  color: var(--ink);
  font-size: var(--text-sm);
}

.ws-mform__inline {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--space-3);
}

.ws-mform__slider {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  max-width: 420px;
}

.ws-mform__value {
  min-width: 32px;
  padding-top: 2px;
  font-weight: 700;
}

.ws-mform__divider {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-2) 0 0;
  color: var(--ink-2);
  font-size: var(--text-xs);
}

.ws-mform__divider::before,
.ws-mform__divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border);
}

.ws-mform__advanced {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-mform__headers {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.ws-mform__header-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) auto;
  gap: var(--space-2);
  width: 100%;
}

.ws-mform__eye {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-mform__muted {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-mform__ok {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: var(--space-2);
  color: var(--status-ok);
  font-size: var(--text-sm);
}

.ws-mform__fail {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--status-danger);
  font-size: var(--text-sm);
}

.ws-mform__error {
  margin: 0;
  color: var(--status-danger);
  font-size: var(--text-xs);
}

.ws-mform__key-hint {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.ws-mform__warn {
  color: var(--status-warn);
}

.ws-mform__result {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.ws-mform__shuttle {
  position: relative;
  display: inline-block;
  width: 80px;
  height: 2px;
  overflow: hidden;
  background: var(--surface-3);
}

.ws-mform__shuttle > span {
  display: block;
  width: 40%;
  height: 100%;
  background: var(--ink);
  animation: ws-shuttle 1.1s var(--ease-move) infinite alternate;
}
</style>
