/**
 * 新建任务的四站流程状态（06 第 6.2 节）。
 * 存在 Pinia 里、不持久化：同一会话里离开再回来，已选的文件和选项还在（06 第 7.5 节）。
 */
import { defineStore } from "pinia"
import { computed, ref, shallowRef } from "vue"
import { filesApi, jobsApi } from "@/api/endpoints"
import type { FileInfo, FilePreview, JobCreate, JobEstimate, JoinMode, TaskType } from "@/api/types"
import { TASK_TYPE_LABEL } from "@/api/types"
import { stripExtension } from "@/utils/text"
import { useModelsStore } from "./models"
import { usePromptsStore } from "./prompts"
import { useSettingsStore } from "./settings"

export type LimitMode = "100" | "custom" | "all"

export const STEP_LABELS = ["选文件", "选数据", "设任务", "开始"] as const

type PerTask<T> = Record<TaskType, T>

export const useNewJobStore = defineStore("newJob", () => {
  const settingsStore = useSettingsStore()
  const promptsStore = usePromptsStore()
  const modelsStore = useModelsStore()

  const step = ref(0)
  const file = ref<FileInfo | null>(null)
  const sheet = ref<string | null>(null)
  const headerRow = ref(1)
  const preview = shallowRef<FilePreview | null>(null)
  const previewLoading = ref(false)
  const previewError = ref<unknown>(null)
  const textColumns = ref<string[]>([])
  const joinMode = ref<JoinMode>("labeled")
  /** 当前文本列是否来自“按平均字数推荐” */
  const suggestedApplied = ref(false)

  const taskType = ref<TaskType>("classify")
  const promptIds = ref<PerTask<number | null>>({ classify: null, summarize: null })
  const modelIds = ref<PerTask<number | null>>({ classify: null, summarize: null })
  const concurrencies = ref<PerTask<number>>({ classify: 5, summarize: 5 })
  /** 用户手动改过的项：切换任务类型时不覆盖 */
  const touched = ref<{ prompt: PerTask<boolean>; model: PerTask<boolean>; concurrency: PerTask<boolean> }>({
    prompt: { classify: false, summarize: false },
    model: { classify: false, summarize: false },
    concurrency: { classify: false, summarize: false },
  })

  const limitMode = ref<LimitMode>("100")
  const customLimit = ref<number | null>(null)
  const startRow = ref<number | null>(null)
  const dedupe = ref(true)
  const maxRetries = ref(2)
  const customName = ref("")

  const estimate = shallowRef<JobEstimate | null>(null)
  const estimating = ref(false)
  const estimateError = ref<unknown>(null)
  let estimateSeq = 0
  let defaultsApplied = false

  function reset() {
    step.value = 0
    file.value = null
    sheet.value = null
    headerRow.value = 1
    preview.value = null
    previewError.value = null
    textColumns.value = []
    joinMode.value = "labeled"
    suggestedApplied.value = false
    customName.value = ""
    startRow.value = null
    customLimit.value = null
    estimate.value = null
    estimateError.value = null
    touched.value = {
      prompt: { classify: false, summarize: false },
      model: { classify: false, summarize: false },
      concurrency: { classify: false, summarize: false },
    }
    defaultsApplied = false
    applyDefaults()
  }

  /** 按设置填好默认值（只填用户没改过的） */
  function applyDefaults() {
    const s = settingsStore.settings
    if (!s) return
    for (const task of ["classify", "summarize"] as TaskType[]) {
      if (!touched.value.prompt[task]) {
        promptIds.value[task] = s.default_prompt_id[task] ?? promptsStore.defaultFor(task)?.id ?? null
      }
      if (!touched.value.model[task]) {
        const id = s.default_model_id[task]
        const model = modelsStore.byId(id)
        modelIds.value[task] = model && model.enabled ? model.id : firstEnabledModelId()
      }
      if (!touched.value.concurrency[task]) concurrencies.value[task] = s.default_concurrency[task]
    }
    if (!defaultsApplied) {
      dedupe.value = s.default_dedupe
      maxRetries.value = s.default_max_retries
      if (s.default_limit === 100) limitMode.value = "100"
      else if (s.default_limit === null) limitMode.value = "all"
      else {
        limitMode.value = "custom"
        customLimit.value = s.default_limit
      }
      defaultsApplied = true
    }
  }

  function firstEnabledModelId(): number | null {
    return modelsStore.visible.find((m) => m.enabled)?.id ?? modelsStore.items.find((m) => m.enabled)?.id ?? null
  }

  const isLines = computed(() => file.value?.kind === "lines")

  /** 选用一个文件，进入“选数据”站 */
  async function selectFile(info: FileInfo) {
    const changed = file.value?.id !== info.id
    file.value = info
    if (changed) {
      sheet.value = info.kind === "table" ? (info.sheets[0]?.name ?? null) : null
      headerRow.value = info.kind === "table" ? 1 : 0
      textColumns.value = []
      joinMode.value = "labeled"
      startRow.value = null
      estimate.value = null
      suggestedApplied.value = false
    }
    step.value = 1
    if (changed || !preview.value) await loadPreview()
  }

  async function loadPreview() {
    if (!file.value) return
    previewLoading.value = true
    previewError.value = null
    try {
      const result = await filesApi.preview(file.value.id, {
        sheet: sheet.value,
        header_row: isLines.value ? 0 : headerRow.value,
        offset: 0,
        limit: 200,
      })
      preview.value = result
      const keys = new Set(result.columns.map((c) => c.key))
      const kept = textColumns.value.filter((k) => keys.has(k))
      if (kept.length > 0) {
        textColumns.value = kept
      } else {
        textColumns.value = [...result.suggested_text_columns]
        suggestedApplied.value = result.suggested_text_columns.length > 0
      }
    } catch (e) {
      previewError.value = e
    } finally {
      previewLoading.value = false
    }
  }

  async function setSheet(name: string) {
    if (sheet.value === name) return
    sheet.value = name
    await loadPreview()
  }

  async function setHeaderRow(row: number) {
    if (headerRow.value === row) return
    headerRow.value = row
    await loadPreview()
  }

  function toggleColumn(key: string) {
    suggestedApplied.value = false
    if (textColumns.value.includes(key)) textColumns.value = textColumns.value.filter((k) => k !== key)
    else textColumns.value = [...textColumns.value, key]
  }

  function setTaskType(task: TaskType) {
    taskType.value = task
    applyDefaults()
  }

  function setPrompt(id: number) {
    promptIds.value[taskType.value] = id
    touched.value.prompt[taskType.value] = true
  }

  function setModel(id: number) {
    modelIds.value[taskType.value] = id
    touched.value.model[taskType.value] = true
  }

  function setConcurrency(value: number) {
    concurrencies.value[taskType.value] = value
    touched.value.concurrency[taskType.value] = true
  }

  const promptId = computed(() => promptIds.value[taskType.value])
  const modelId = computed(() => modelIds.value[taskType.value])
  const concurrency = computed(() => concurrencies.value[taskType.value])

  const limitValue = computed<number | null>(() => {
    if (limitMode.value === "100") return 100
    if (limitMode.value === "all") return null
    return customLimit.value && customLimit.value > 0 ? Math.min(100_000, Math.floor(customLimit.value)) : null
  })

  const autoName = computed(() =>
    file.value ? `${stripExtension(file.value.original_name)} ${TASK_TYPE_LABEL[taskType.value]}` : "",
  )

  const jobName = computed(() => customName.value.trim() || autoName.value)

  /** 拼接后的第一条数据（“第一条将这样发给模型”） */
  const firstItemPreview = computed(() => {
    const p = preview.value
    if (!p || textColumns.value.length === 0) return ""
    const titles = new Map(p.columns.map((c) => [c.key, c.title]))
    for (const row of p.rows) {
      const parts: string[] = []
      for (const key of textColumns.value) {
        const value = (row.values[key] ?? "").trim()
        if (!value) continue
        parts.push(joinMode.value === "labeled" && textColumns.value.length > 1 ? `${titles.get(key) ?? key}：${value}` : value)
      }
      const text = parts.join("\n")
      if (text) return text
    }
    return ""
  })

  /** 组装 JobCreate；条件不完整时返回 null */
  function buildBody(): JobCreate | null {
    if (!file.value || textColumns.value.length === 0 || promptId.value === null || modelId.value === null) return null
    if (limitMode.value === "custom" && limitValue.value === null) return null
    return {
      name: customName.value.trim() || undefined,
      task_type: taskType.value,
      file_id: file.value.id,
      source: {
        sheet: isLines.value ? null : sheet.value,
        header_row: isLines.value ? 0 : headerRow.value,
        text_columns: [...textColumns.value],
        join_mode: joinMode.value,
        start_row: startRow.value && startRow.value > 0 ? Math.floor(startRow.value) : null,
        limit: limitValue.value,
        split_mode: "line",
      },
      prompt_id: promptId.value,
      model_id: modelId.value,
      concurrency: concurrency.value,
      max_retries: maxRetries.value,
      dedupe: dedupe.value,
    }
  }

  async function refreshEstimate(): Promise<void> {
    const body = buildBody()
    if (!body) {
      estimate.value = null
      return
    }
    const seq = ++estimateSeq
    estimating.value = true
    try {
      const result = await jobsApi.estimate(body)
      if (seq === estimateSeq) {
        estimate.value = result
        estimateError.value = null
      }
    } catch (e) {
      if (seq === estimateSeq) {
        estimate.value = null
        estimateError.value = e
      }
    } finally {
      if (seq === estimateSeq) estimating.value = false
    }
  }

  return {
    step,
    file,
    sheet,
    headerRow,
    preview,
    previewLoading,
    previewError,
    textColumns,
    joinMode,
    suggestedApplied,
    taskType,
    promptIds,
    modelIds,
    concurrencies,
    touched,
    limitMode,
    customLimit,
    startRow,
    dedupe,
    maxRetries,
    customName,
    estimate,
    estimating,
    estimateError,
    isLines,
    promptId,
    modelId,
    concurrency,
    limitValue,
    autoName,
    jobName,
    firstItemPreview,
    reset,
    applyDefaults,
    selectFile,
    loadPreview,
    setSheet,
    setHeaderRow,
    toggleColumn,
    setTaskType,
    setPrompt,
    setModel,
    setConcurrency,
    buildBody,
    refreshEstimate,
  }
})
