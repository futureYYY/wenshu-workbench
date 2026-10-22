<script setup lang="ts">
// 设置（06 第 6.9 节）：分组的单栏表单，修改后立即保存，toast“已保存”。
import { FolderOpen } from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { systemApi } from "@/api/endpoints"
import type { RunMode, SettingsPatch, ThemeSetting } from "@/api/types"
import Button from "@/components/base/Button.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import FieldRow from "@/components/base/FieldRow.vue"
import NumberInput from "@/components/base/NumberInput.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import Slider from "@/components/base/Slider.vue"
import Switch from "@/components/base/Switch.vue"
import { useModelsStore } from "@/stores/models"
import { useSettingsStore } from "@/stores/settings"
import { useUiStore } from "@/stores/ui"
import { notify, notifyError } from "@/utils/toast"

const store = useSettingsStore()
const ui = useUiStore()
const models = useModelsStore()

const RUN_MODE_LABEL: Record<RunMode, string> = { exe: "打包版", source: "源码版", dev: "开发模式" }

const classifyConcurrency = ref(5)
const summarizeConcurrency = ref(5)
const limitMode = ref("100")
const customLimit = ref<number | null>(500)
const retries = ref<number | null>(2)
const port = ref<number | null>(18765)

function syncLocal() {
  const s = store.settings
  if (!s) return
  classifyConcurrency.value = s.default_concurrency.classify
  summarizeConcurrency.value = s.default_concurrency.summarize
  if (s.default_limit === null) limitMode.value = "all"
  else if (s.default_limit === 100) limitMode.value = "100"
  else {
    limitMode.value = "custom"
    customLimit.value = s.default_limit
  }
  retries.value = s.default_max_retries
  port.value = s.preferred_port
}

watch(() => store.settings, syncLocal, { immediate: true })

onMounted(() => {
  void store.load(true).catch((e) => notifyError(e))
})

async function save(patch: SettingsPatch, message = "已保存") {
  try {
    await store.patch(patch)
    notify(message)
  } catch (e) {
    notifyError(e)
    syncLocal()
  }
}

// 拖动滑块时停顿 400 ms 再保存
const timers = new Map<string, number>()
function debounced(key: string, fn: () => void, delay = 400) {
  window.clearTimeout(timers.get(key))
  timers.set(key, window.setTimeout(fn, delay))
}

onBeforeUnmount(() => {
  for (const t of timers.values()) window.clearTimeout(t)
})

watch(classifyConcurrency, (value) => {
  if (store.settings && value !== store.settings.default_concurrency.classify) {
    debounced("cc", () => void save({ default_concurrency: { classify: value } }))
  }
})

watch(summarizeConcurrency, (value) => {
  if (store.settings && value !== store.settings.default_concurrency.summarize) {
    debounced("sc", () => void save({ default_concurrency: { summarize: value } }))
  }
})

const limitModel = computed({
  get: () => limitMode.value,
  set: (value: string) => {
    limitMode.value = value
    if (value === "100") void save({ default_limit: 100 })
    else if (value === "all") void save({ default_limit: null })
    else if (customLimit.value && customLimit.value > 0) void save({ default_limit: customLimit.value })
  },
})

function commitCustomLimit(value: number | null) {
  if (value && value > 0) void save({ default_limit: value })
}

function commitRetries(value: number | null) {
  if (value !== null && store.settings && value !== store.settings.default_max_retries) void save({ default_max_retries: value })
}

function commitPort(value: number | null) {
  if (value !== null && store.settings && value !== store.settings.preferred_port) void save({ preferred_port: value }, "已保存，重启后生效")
}

const dedupe = computed({
  get: () => store.settings?.default_dedupe ?? true,
  set: (value: boolean) => void save({ default_dedupe: value }),
})

async function setShowDemo(value: boolean) {
  await save({ show_demo_model: value })
  void models.load(true)
}

const showDemo = computed({
  get: () => store.settings?.show_demo_model ?? true,
  set: (value: boolean) => void setShowDemo(value),
})

const openMode = computed({
  get: () => store.settings?.open_mode ?? "app",
  set: (value: string) => void save({ open_mode: value === "browser" ? "browser" : "app" }, "已保存，下次启动生效"),
})

const THEMES: { value: ThemeSetting; label: string }[] = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "亮色" },
  { value: "dark", label: "暗色" },
]

async function setTheme(value: ThemeSetting) {
  ui.setTheme(value)
  await save({ theme: value })
}

function onThemeKeydown(event: KeyboardEvent) {
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return
  event.preventDefault()
  const index = THEMES.findIndex((t) => t.value === ui.themeSetting)
  const dir = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1
  const next = THEMES[(index + dir + THEMES.length) % THEMES.length]
  if (next) {
    void setTheme(next.value)
    ;(document.querySelector(`[data-theme-option="${next.value}"]`) as HTMLElement | null)?.focus()
  }
}

async function openFolder(target: "data" | "logs") {
  try {
    await systemApi.openFolder(target)
  } catch (e) {
    notifyError(e)
  }
}
</script>

<template>
  <div class="ws-settings">
    <div v-if="!store.settings && !store.error" class="ws-settings__skeleton">
      <Skeleton v-for="i in 6" :key="i" height="36px" />
    </div>
    <EmptyState v-else-if="!store.settings" tone="danger" title="设置没有加载出来" :description="(store.error as Error)?.message">
      <Button variant="primary" @click="store.load(true)">重新加载</Button>
    </EmptyState>

    <template v-else>
      <section class="ws-settings__group" aria-labelledby="set-defaults">
        <h2 id="set-defaults" class="ws-settings__title">任务默认值</h2>
        <FieldRow label="意图识别并发" align="start">
          <div class="ws-settings__slider">
            <Slider v-model="classifyConcurrency" :min="1" :max="store.limits.max_concurrency" :ticks="[1, 5, 10, 15, 20]" :default-value="5" aria-label="意图识别默认并发" />
            <span class="num ws-settings__value">{{ classifyConcurrency }}</span>
          </div>
        </FieldRow>
        <FieldRow label="文本摘要并发" align="start">
          <div class="ws-settings__slider">
            <Slider v-model="summarizeConcurrency" :min="1" :max="store.limits.max_concurrency" :ticks="[1, 5, 10, 15, 20]" :default-value="5" aria-label="文本摘要默认并发" />
            <span class="num ws-settings__value">{{ summarizeConcurrency }}</span>
          </div>
        </FieldRow>
        <FieldRow label="处理条数">
          <div class="ws-settings__inline">
            <SegmentedControl
              v-model="limitModel"
              aria-label="默认处理条数"
              :options="[
                { value: '100', label: '100' },
                { value: 'custom', label: '自定义' },
                { value: 'all', label: '全部' },
              ]"
            />
            <NumberInput
              v-if="limitMode === 'custom'"
              v-model="customLimit"
              :min="1"
              :max="store.limits.max_rows_per_source"
              :width="120"
              unit="条"
              aria-label="自定义默认处理条数"
              @commit="commitCustomLimit"
            />
          </div>
        </FieldRow>
        <FieldRow label="失败重试次数" hint="0 到 5 次">
          <NumberInput v-model="retries" :min="0" :max="5" :width="100" unit="次" aria-label="默认失败重试次数" @commit="commitRetries" />
        </FieldRow>
        <FieldRow label="相同文本只调用一次" hint="同一任务内文本完全相同的条目只请求一次，结果共享">
          <Switch v-model="dedupe" aria-label="相同文本只调用一次" />
        </FieldRow>
      </section>

      <section class="ws-settings__group" aria-labelledby="set-look">
        <h2 id="set-look" class="ws-settings__title">外观</h2>
        <div class="ws-settings__themes" role="radiogroup" aria-label="主题" @keydown="onThemeKeydown">
          <button
            v-for="t in THEMES"
            :key="t.value"
            type="button"
            role="radio"
            class="ws-theme"
            :class="{ 'is-active': ui.themeSetting === t.value }"
            :aria-checked="ui.themeSetting === t.value"
            :tabindex="ui.themeSetting === t.value ? 0 : -1"
            :data-theme-option="t.value"
            @click="setTheme(t.value)"
          >
            <span class="ws-theme__preview" aria-hidden="true">
              <template v-if="t.value === 'system'">
                <span class="ws-theme__half" data-theme="light"><span class="ws-theme__mini" /></span>
                <span class="ws-theme__half" data-theme="dark"><span class="ws-theme__mini" /></span>
              </template>
              <span v-else class="ws-theme__full" :data-theme="t.value"><span class="ws-theme__mini" /></span>
            </span>
            <span class="ws-theme__label">{{ t.label }}</span>
          </button>
        </div>
      </section>

      <section class="ws-settings__group" aria-labelledby="set-start">
        <h2 id="set-start" class="ws-settings__title">启动</h2>
        <FieldRow label="打开方式">
          <SegmentedControl
            v-model="openMode"
            aria-label="打开方式"
            :options="[
              { value: 'app', label: '独立窗口' },
              { value: 'browser', label: '默认浏览器' },
            ]"
          />
        </FieldRow>
        <FieldRow label="端口" hint="被占用时自动换一个空闲端口；重启后生效">
          <NumberInput v-model="port" :min="1024" :max="65535" :width="120" aria-label="端口" @commit="commitPort" />
        </FieldRow>
      </section>

      <section class="ws-settings__group" aria-labelledby="set-data">
        <h2 id="set-data" class="ws-settings__title">数据</h2>
        <FieldRow label="运行方式">
          <span>{{ store.info ? RUN_MODE_LABEL[store.info.run_mode] : "—" }}</span>
        </FieldRow>
        <FieldRow label="数据目录" align="start">
          <div class="ws-settings__inline">
            <span class="mono ws-settings__path">{{ store.info?.data_dir ?? "—" }}</span>
            <Button variant="secondary" size="sm" @click="openFolder('data')">
              <template #icon><FolderOpen :size="14" :stroke-width="1.75" /></template>
              打开
            </Button>
          </div>
          <template #hint>
            API Key 加密保存在本机，加密用的密钥是数据目录里的 secret.key，删除它会让已保存的 API Key 失效。
            它能防止数据库文件被单独拷走后泄露密钥，但挡不住能登录这台电脑的人。
          </template>
        </FieldRow>
        <FieldRow label="日志目录">
          <Button variant="secondary" size="sm" @click="openFolder('logs')">
            <template #icon><FolderOpen :size="14" :stroke-width="1.75" /></template>
            打开
          </Button>
        </FieldRow>
        <FieldRow label="版本号">
          <span class="num">{{ store.info?.version ?? "—" }}</span>
        </FieldRow>
        <FieldRow label="字体">
          <span class="ws-settings__muted">Noto Sans SC、Overpass、Overpass Mono，均为 SIL Open Font License</span>
        </FieldRow>
      </section>

      <section class="ws-settings__group" aria-labelledby="set-demo">
        <h2 id="set-demo" class="ws-settings__title">演示模型</h2>
        <FieldRow label="在模型列表中显示演示模型" hint="演示模型不需要密钥、不联网，结果是模拟的">
          <Switch v-model="showDemo" aria-label="在模型列表中显示演示模型" />
        </FieldRow>
      </section>
    </template>
  </div>
</template>

<style scoped>
.ws-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  max-width: var(--form-max);
  padding-top: var(--space-2);
}

.ws-settings__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-settings__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding-bottom: var(--space-8);
  border-bottom: 1px solid var(--border);
}

.ws-settings__group:last-child {
  border-bottom: 0;
}

.ws-settings__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 500;
}

.ws-settings__slider {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  max-width: 480px;
}

.ws-settings__value {
  min-width: 28px;
  padding-top: 2px;
  font-size: var(--text-lg);
  font-weight: 700;
  text-align: right;
}

.ws-settings__inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ws-settings__path {
  overflow-wrap: anywhere;
  font-size: var(--text-sm);
}

.ws-settings__muted {
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-settings__themes {
  display: flex;
  gap: var(--space-4);
}

.ws-theme {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-panel);
  background: transparent;
  color: var(--ink);
}

.ws-theme.is-active .ws-theme__preview {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

.ws-theme__preview {
  display: flex;
  width: 132px;
  height: 84px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
}

.ws-theme__half,
.ws-theme__full {
  position: relative;
  flex: 1;
  background: var(--bg);
}

.ws-theme__mini {
  position: absolute;
  inset: 10px 10px 10px 22px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
}

.ws-theme__mini::before {
  content: "";
  position: absolute;
  top: 10px;
  left: 8px;
  width: 40%;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--ink);
}

.ws-theme__mini::after {
  content: "";
  position: absolute;
  top: 22px;
  left: 8px;
  width: 60%;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--line-0);
}

.ws-theme__half .ws-theme__mini {
  inset: 10px 6px 10px 10px;
}

.ws-theme__label {
  font-size: var(--text-sm);
}
</style>
