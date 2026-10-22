<script setup lang="ts">
// 组件预览页（08 阶段 3 T3-7）：展示每个组件的每种状态，可切换主题。只在开发模式注册路由。
import { Pencil, Trash2 } from "@lucide/vue"
import { computed, onBeforeUnmount, ref } from "vue"
import type {
  CategoryStat,
  FilePreview,
  ItemStatus,
  JobProgress,
  JobStatus,
  PromptVariable,
  ThemeSetting,
  Track,
} from "@/api/types"
import AnimatedNumber from "@/components/base/AnimatedNumber.vue"
import Button from "@/components/base/Button.vue"
import Collapsible from "@/components/base/Collapsible.vue"
import Combobox from "@/components/base/Combobox.vue"
import Dialog from "@/components/base/Dialog.vue"
import Drawer from "@/components/base/Drawer.vue"
import DropdownMenu from "@/components/base/DropdownMenu.vue"
import EmptyState from "@/components/base/EmptyState.vue"
import IconButton from "@/components/base/IconButton.vue"
import Input from "@/components/base/Input.vue"
import Kbd from "@/components/base/Kbd.vue"
import Logo from "@/components/base/Logo.vue"
import NumberInput from "@/components/base/NumberInput.vue"
import Popover from "@/components/base/Popover.vue"
import SegmentedControl from "@/components/base/SegmentedControl.vue"
import Select from "@/components/base/Select.vue"
import Skeleton from "@/components/base/Skeleton.vue"
import Slider from "@/components/base/Slider.vue"
import StatusChip from "@/components/base/StatusChip.vue"
import Switch from "@/components/base/Switch.vue"
import Tabs from "@/components/base/Tabs.vue"
import Textarea from "@/components/base/Textarea.vue"
import Tooltip from "@/components/base/Tooltip.vue"
import PreviewGrid from "@/components/data/PreviewGrid.vue"
import JsonView from "@/components/editor/JsonView.vue"
import PromptEditor from "@/components/editor/PromptEditor.vue"
import CompressionGauge from "@/components/metro/CompressionGauge.vue"
import ExpressTrace from "@/components/metro/ExpressTrace.vue"
import LineBadge from "@/components/metro/LineBadge.vue"
import LineMap from "@/components/metro/LineMap.vue"
import LineProgress from "@/components/metro/LineProgress.vue"
import MetroStepper from "@/components/metro/MetroStepper.vue"
import ParallelTracks from "@/components/metro/ParallelTracks.vue"
import StationDot from "@/components/metro/StationDot.vue"
import { LINE_NAMES } from "@/design/palette"
import { useUiStore } from "@/stores/ui"
import { notify, notifyUndo } from "@/utils/toast"

const ui = useUiStore()
const themes: { value: ThemeSetting; label: string }[] = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "亮色" },
  { value: "dark", label: "暗色" },
]

const text = ref("示例文本")
const num = ref<number | null>(120)
const area = ref("每行一条数据")
const selectValue = ref<string | undefined>("a")
const combo = ref("deepseek-chat")
const seg = ref("100")
const slider = ref(5)
const temp = ref(0.3)
const sw = ref(true)
const tab = ref("result")
const drawerOpen = ref(false)
const dialogOpen = ref(false)
const collapseOpen = ref(false)
const step = ref(1)
const counter = ref(1284)

const jobStatuses: JobStatus[] = ["queued", "running", "paused", "completed", "cancelled"]
const itemStatuses: ItemStatus[] = ["pending", "running", "succeeded", "failed", "skipped"]
const stationStates = ["todo", "current", "done", "error", "paused"] as const
const stationSizes = [8, 12, 16, 64] as const

function progress(succeeded: number, failed: number, skipped: number, total: number, running = 0): JobProgress {
  const done = succeeded + failed + skipped
  return {
    total,
    pending: Math.max(0, total - done - running),
    running,
    succeeded,
    failed,
    skipped,
    percent: Math.round((done / total) * 1000) / 10,
    rate_per_min: 42,
    eta_seconds: 50,
  }
}

const categories = ref<CategoryStat[]>([
  { label: "物流查询", count: 412, percent: 32.1, color_index: 0 },
  { label: "退款咨询", count: 388, percent: 30.2, color_index: 1 },
  { label: "账号问题", count: 251, percent: 19.5, color_index: 2 },
  { label: "会员办理", count: 147, percent: 11.4, color_index: 3 },
  { label: "其他", count: 86, percent: 6.7, color_index: 4 },
])

const manyCategories = computed<CategoryStat[]>(() =>
  Array.from({ length: 14 }, (_, i) => ({
    label: `意图 ${i + 1}`,
    count: 200 - i * 12,
    percent: Math.round(((200 - i * 12) / 1790) * 1000) / 10,
    color_index: i < 11 ? i : -1,
  })),
)

const mapSelected = ref<string[]>([])

function toggleMap(labels: string[], additive: boolean) {
  const set = new Set(additive ? mapSelected.value : [])
  for (const l of labels) {
    if (mapSelected.value.includes(l) && !additive) {
      mapSelected.value = []
      return
    }
    if (set.has(l)) set.delete(l)
    else set.add(l)
  }
  mapSelected.value = Array.from(set)
}

function addCategory() {
  const n = categories.value.length
  categories.value = [
    ...categories.value,
    { label: `新意图 ${n + 1}`, count: 20 + n, percent: 1.5, color_index: n < 11 ? n : -1 },
  ]
}

const now = Date.now()
const tracks = ref<Track[]>([
  { item_id: 63, seq: 62, row_number: 63, input_preview: "我想问一下退款多久能到账，已经三天了", started_at: new Date(now - 2100).toISOString(), attempt: 1, phase: "request", phase_detail: "", retry_at: null },
  { item_id: 64, seq: 63, row_number: 64, input_preview: "快递一直显示在途，能帮我查一下吗", started_at: new Date(now - 1400).toISOString(), attempt: 1, phase: "chunk", phase_detail: "第 2/5 段", retry_at: null },
  { item_id: 66, seq: 65, row_number: 66, input_preview: "会员自动续费怎么关", started_at: new Date(now - 4000).toISOString(), attempt: 2, phase: "waiting_retry", phase_detail: "限流，3 秒后重试", retry_at: new Date(now + 3000).toISOString() },
  { item_id: 67, seq: 66, row_number: 67, input_preview: "积分什么时候过期", started_at: new Date(now - 900).toISOString(), attempt: 2, phase: "parse_repair", phase_detail: "纠正输出格式", retry_at: null },
])

const preview: FilePreview = {
  sheet: "对话",
  header_row: 1,
  columns: [
    { key: "会话ID", title: "会话ID", letter: "A", index: 0, avg_chars: 5, empty_ratio: 0, numeric_ratio: 1 },
    { key: "用户问题", title: "用户问题", letter: "B", index: 1, avg_chars: 34, empty_ratio: 0, numeric_ratio: 0 },
    { key: "渠道", title: "渠道", letter: "C", index: 2, avg_chars: 2, empty_ratio: 0, numeric_ratio: 0 },
  ],
  suggested_text_columns: ["用户问题"],
  rows: [
    { row_number: 2, values: { 会话ID: "10023", 用户问题: "我的快递三天没动了，能帮我查一下吗", 渠道: "App" } },
    { row_number: 3, values: { 会话ID: "10024", 用户问题: "会员怎么退订", 渠道: "电话" } },
  ],
  total_rows: 2,
  blank_rows: 0,
  truncated: false,
}
const previewSelected = ref<string[]>(["用户问题"])

function togglePreview(key: string) {
  previewSelected.value = previewSelected.value.includes(key)
    ? previewSelected.value.filter((k) => k !== key)
    : [...previewSelected.value, key]
}

const variables: PromptVariable[] = [
  { name: "text", insert: "{{text}}", description: "本条文本", templates: ["system", "user", "chunk", "merge"] },
  { name: "row_number", insert: "{{row_number}}", description: "原文件行号", templates: ["system", "user", "chunk", "merge"] },
  { name: "col:", insert: "{{col:}}", description: "该行某一列的值", templates: ["system", "user", "chunk", "merge"] },
]
const editorText = ref("请识别下面这段文本的意图：\n\n{{text}}\n\n未知变量示例：{{foo}}")

const segments = [
  "第一段：用户反映快递三天没有更新物流信息。",
  "第二段：客服查询后发现包裹滞留在中转站。",
  "第三段：客服承诺联系快递公司加急处理，并在明天回电。",
]
const keyPoints = [
  { text: "快递三天没有更新", sources: [1] },
  { text: "包裹滞留在中转站", sources: [2] },
  { text: "承诺加急并回电", sources: [3] },
]

const timer = window.setInterval(() => {
  counter.value += Math.round(Math.random() * 40)
}, 2500)
onBeforeUnmount(() => window.clearInterval(timer))

const menuItems = [
  { label: "编辑", icon: Pencil, shortcut: "e", onSelect: () => notify("选了编辑") },
  { separator: true, label: "" },
  { label: "删除", icon: Trash2, danger: true, onSelect: () => notify("选了删除") },
]
</script>

<template>
  <div class="ws-dev">
    <div class="ws-dev__themes">
      <span>主题</span>
      <Button
        v-for="t in themes"
        :key="t.value"
        size="sm"
        :variant="ui.themeSetting === t.value ? 'primary' : 'secondary'"
        @click="ui.setTheme(t.value)"
      >
        {{ t.label }}
      </Button>
    </div>

    <section class="ws-dev__section">
      <h2>导视数字等宽检查</h2>
      <div class="ws-dev__nums">
        <span class="num">111,111</span>
        <span class="num">888,888</span>
        <AnimatedNumber :value="counter" />
      </div>
      <p class="ws-dev__hint">上下两行宽度必须一致；第三行每 2.5 秒滚动一次。</p>
      <Logo :size="28" label="文枢" />
      <Logo :size="64" />
    </section>

    <section class="ws-dev__section">
      <h2>Button</h2>
      <div v-for="size in ['sm', 'md', 'lg'] as const" :key="size" class="ws-dev__row">
        <Button variant="primary" :size="size">主按钮</Button>
        <Button variant="secondary" :size="size">次按钮</Button>
        <Button variant="text" :size="size">文字按钮</Button>
        <Button variant="danger" :size="size">删除任务</Button>
        <Button variant="primary" :size="size" loading>开始处理</Button>
        <Button variant="secondary" :size="size" disabled>禁用</Button>
      </div>
      <div class="ws-dev__row">
        <IconButton label="编辑" shortcut="e"><Pencil :size="16" :stroke-width="1.75" /></IconButton>
        <IconButton label="删除" disabled><Trash2 :size="16" :stroke-width="1.75" /></IconButton>
        <Tooltip content="提示文字" shortcut="ctrl+k"><Button size="sm">悬停看提示</Button></Tooltip>
        <Kbd>Ctrl</Kbd><Kbd>K</Kbd>
      </div>
    </section>

    <section class="ws-dev__section">
      <h2>输入</h2>
      <div class="ws-dev__grid">
        <Input v-model="text" placeholder="占位文字" />
        <Input v-model="text" error="不能超过 40 个字" />
        <Input v-model="text" disabled />
        <Input v-model="text" :maxlength="40" show-count />
        <NumberInput v-model="num" :min="16" :max="32768" unit="tokens" />
        <NumberInput v-model="num" error="必须在 1 到 20 之间" />
        <Textarea v-model="area" :rows="3" />
        <Combobox v-model="combo" :options="['deepseek-chat', 'deepseek-reasoner', 'qwen3:14b']" mono />
        <Select
          v-model="selectValue"
          :options="[
            { value: 'a', label: '默认意图识别', hint: 'v3' },
            { value: 'b', label: '电商售后意图', description: '自定义模板' },
            { value: 'c', label: '已停用的模型', disabled: true },
          ]"
          aria-label="示例选择"
        />
      </div>
    </section>

    <section class="ws-dev__section">
      <h2>选择类</h2>
      <div class="ws-dev__row">
        <SegmentedControl
          v-model="seg"
          aria-label="示例分段"
          :options="[
            { value: '100', label: '100' },
            { value: 'custom', label: '自定义' },
            { value: 'all', label: '全部', count: '5,032' },
          ]"
        />
        <Switch v-model="sw" aria-label="示例开关" />
        <Switch :model-value="false" disabled aria-label="禁用的开关" />
      </div>
      <div class="ws-dev__row ws-dev__wide">
        <Slider v-model="slider" :min="1" :max="20" :ticks="[1, 5, 10, 15, 20]" :default-value="5" aria-label="并发" />
        <Slider v-model="temp" :min="0" :max="2" :step="0.1" :ticks="[0, 1, 2]" aria-label="温度" />
      </div>
      <Tabs
        v-model="tab"
        :items="[
          { value: 'result', label: '结果' },
          { value: 'input', label: '原文' },
          { value: 'attempts', label: '尝试记录' },
        ]"
      />
      <Collapsible v-model:open="collapseOpen" title="输出解析" summary="JSON  intent / confidence / reason">
        <p>折叠面板的内容。</p>
      </Collapsible>
    </section>

    <section class="ws-dev__section">
      <h2>浮层</h2>
      <div class="ws-dev__row">
        <Button @click="drawerOpen = true">打开抽屉</Button>
        <Button @click="dialogOpen = true">打开对话框</Button>
        <DropdownMenu :items="menuItems">
          <template #trigger><Button>下拉菜单</Button></template>
        </DropdownMenu>
        <Popover>
          <template #trigger><Button>弹出层</Button></template>
          <p>弹出层里的内容。</p>
        </Popover>
        <Button @click="notify('已保存为 v8')">toast</Button>
        <Button @click="notifyUndo('已删除任务“示例”', () => notify('已真正删除'), () => notify('已撤销'))">可撤销的 toast</Button>
      </div>
      <Drawer v-model:open="drawerOpen" title="抽屉标题">
        <p>抽屉内容。按 Esc 关闭。</p>
        <template #footer><Button variant="primary" @click="drawerOpen = false">完成</Button></template>
      </Drawer>
      <Dialog v-model:open="dialogOpen" title="删除任务" description="“示例任务”的 12 条结果会一起删除，删除后不能恢复。">
        <template #actions>
          <Button variant="secondary" @click="dialogOpen = false">取消</Button>
          <Button variant="danger" @click="dialogOpen = false">删除任务</Button>
        </template>
      </Dialog>
    </section>

    <section class="ws-dev__section">
      <h2>状态</h2>
      <div class="ws-dev__row">
        <StatusChip v-for="s in jobStatuses" :key="s" :status="s" />
      </div>
      <div class="ws-dev__row">
        <StatusChip v-for="s in itemStatuses" :key="s" :status="s" kind="item" />
      </div>
      <div class="ws-dev__row">
        <Skeleton width="160px" />
        <Skeleton width="80px" height="22px" radius="9999px" />
      </div>
      <EmptyState title="还没有任务。把文件拖进窗口就能开始第一个。" description="空状态是一次邀请。">
        <Button variant="primary">新建任务</Button>
      </EmptyState>
    </section>

    <section class="ws-dev__section">
      <h2>线路徽标与站点</h2>
      <div class="ws-dev__row">
        <LineBadge v-for="(name, i) in LINE_NAMES" :key="name" :label="name" :color-index="i" />
        <LineBadge label="其他" :color-index="-1" />
      </div>
      <div class="ws-dev__row">
        <LineBadge label="物流查询" :color-index="0" :count="412" size="md" />
        <LineBadge label="一个特别特别长的意图名称会被省略显示" :color-index="2" size="md" selected />
      </div>
      <div v-for="size in stationSizes" :key="size" class="ws-dev__row">
        <StationDot v-for="st in stationStates" :key="st" :size="size" :state="st" />
        <StationDot :size="size" state="todo" :progress="0.6" />
      </div>
    </section>

    <section class="ws-dev__section">
      <h2>步骤条</h2>
      <MetroStepper :steps="['选文件', '选数据', '设任务', '开始']" :current="step" @go="step = $event" />
      <div class="ws-dev__row">
        <Button size="sm" @click="step = Math.max(0, step - 1)">上一站</Button>
        <Button size="sm" @click="step = Math.min(3, step + 1)">下一站</Button>
      </div>
      <MetroStepper :steps="['始发站', '选数据', '设任务', '开始']" :current="0" origin armed :scale="1.08" />
      <MetroStepper :steps="['始发站', '选数据', '设任务', '开始']" :current="0" origin :progress="0.35" />
    </section>

    <section class="ws-dev__section">
      <h2>线路进度</h2>
      <div class="ws-dev__col">
        <LineProgress :progress="progress(60, 2, 0, 100, 5)" status="running" />
        <LineProgress :progress="progress(12, 0, 1, 40)" status="paused" />
        <LineProgress :progress="progress(298, 2, 0, 300)" status="completed" />
        <LineProgress :progress="progress(20, 0, 0, 300)" status="cancelled" />
        <LineProgress
          variant="full"
          :progress="progress(60, 2, 3, 100, 5)"
          status="running"
          :started-at="new Date(now - 90000).toISOString()"
        />
        <LineProgress
          variant="full"
          :progress="progress(98, 2, 0, 100)"
          status="completed"
          :started-at="new Date(now - 133000).toISOString()"
          :finished-at="new Date(now).toISOString()"
        />
      </div>
    </section>

    <section class="ws-dev__section">
      <h2>线网图</h2>
      <div class="ws-dev__row">
        <Button size="sm" @click="addCategory">开通一条新线路</Button>
      </div>
      <div class="ws-dev__map">
        <LineMap :categories="categories" :failed="12" running :selected="mapSelected" :height="380" @toggle="toggleMap" />
      </div>
      <div class="ws-dev__map">
        <LineMap :categories="manyCategories" :failed="0" :running="false" :height="680" />
      </div>
      <div class="ws-dev__map is-small">
        <LineMap :categories="[]" :failed="0" running :height="200" />
      </div>
    </section>

    <section class="ws-dev__section">
      <h2>并行轨道</h2>
      <div class="ws-dev__panel">
        <ParallelTracks :tracks="tracks" :concurrency="5" status="running" />
      </div>
      <div class="ws-dev__panel">
        <ParallelTracks :tracks="[]" :concurrency="5" status="paused" />
      </div>
    </section>

    <section class="ws-dev__section">
      <h2>浓缩计与对照阅读</h2>
      <CompressionGauge :input-chars="6240" :output-chars="412" />
      <div class="ws-dev__trace">
        <ExpressTrace :segments="segments" summary="用户反映快递滞留，客服承诺加急处理。" :key-points="keyPoints" />
      </div>
    </section>

    <section class="ws-dev__section">
      <h2>数据预览与编辑器</h2>
      <PreviewGrid :preview="preview" :selected="previewSelected" suggested @toggle="togglePreview" />
      <JsonView :value="{ intent: '物流查询', confidence: 0.94, reason: '询问物流进度', ok: true, extra: null }" />
      <JsonView value="好的，我认为这是咨询" raw />
      <PromptEditor v-model="editorText" label="用户消息模板" template-slot="user" :variables="variables" />
      <PromptEditor :model-value="editorText" label="只读" template-slot="user" :variables="variables" readonly />
    </section>
  </div>
</template>

<style scoped>
.ws-dev {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
  max-width: 1280px;
  padding-bottom: var(--space-16);
}

.ws-dev__themes {
  position: sticky;
  top: var(--pagebar-height);
  z-index: var(--z-header);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  background: var(--bg);
}

.ws-dev__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-dev__section h2 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 500;
}

.ws-dev__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ws-dev__wide > * {
  max-width: 420px;
}

.ws-dev__col {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.ws-dev__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.ws-dev__nums {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: var(--text-num-l);
  font-weight: 800;
  line-height: 1.2;
}

.ws-dev__hint {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-dev__map {
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
}

.ws-dev__panel {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: var(--surface);
}

.ws-dev__trace {
  height: 360px;
}
</style>
