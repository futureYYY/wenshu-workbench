/**
 * 接口类型的别名。组件和 store 只从这里取类型，不直接引用 schema.d.ts，
 * 重新生成 schema.d.ts 后如有差异，只需要改这个文件。
 */
import type { components } from "./schema"

type Schemas = components["schemas"]

export type Health = Schemas["Health"]
export type SystemInfo = Schemas["SystemInfo"]
export type Settings = Schemas["Settings"]
export type SettingsPatch = Schemas["SettingsPatch"]

export type ModelConfig = Schemas["ModelConfig"]
export type ModelConfigInput = Schemas["ModelConfigInput"]
export type ModelConfigPatch = Schemas["ModelConfigPatch"]
export type ModelDraftRequest = Schemas["ModelDraftRequest"]
export type ModelTestResult = Schemas["ModelTestResult"]
export type LastTest = Schemas["LastTest"]

export type PromptTemplate = Schemas["PromptTemplate"]
export type PromptDraft = Schemas["PromptDraft"]
export type PromptInput = Schemas["PromptInput"]
export type PromptCopy = Schemas["PromptCopy"]
export type PromptSnapshot = Schemas["PromptSnapshot"]
export type PromptVariable = Schemas["PromptVariable"]
export type PromptVersionSummary = Schemas["PromptVersionSummary"]
export type PromptVersionDetail = Schemas["PromptVersionDetail"]
export type ClassifyFieldMap = Schemas["ClassifyFieldMap"]
export type SummarizeFieldMap = Schemas["SummarizeFieldMap"]
export type FieldMap = ClassifyFieldMap | SummarizeFieldMap
export type SampleText = Schemas["SampleText"]
export type SampleRow = Schemas["SampleRow"]
export type Sample = SampleText | SampleRow
export type RenderRequest = Schemas["RenderRequest"]
export type RenderResult = Schemas["RenderResult"]
export type ChatMessage = Schemas["ChatMessage"]
export type ClassifyResult = Schemas["ClassifyResult"]
export type SummarizeResult = Schemas["SummarizeResult"]
export type KeyPoint = Schemas["KeyPoint"]
export type Usage = Schemas["Usage"]

export type PlaygroundRunRequest = Schemas["PlaygroundRunRequest"]

export type FileInfo = Schemas["FileInfo"]
export type FilePreview = Schemas["FilePreview"]
export type ColumnInfo = Schemas["ColumnInfo"]
export type PreviewRow = Schemas["PreviewRow"]
export type SheetInfo = Schemas["SheetInfo"]

export type JobCreate = Schemas["JobCreate"]
export type JobSourceInput = Schemas["JobSourceInput"]
/**
 * 预估结果。est_seconds 在后端是 tuple[int, int]（预计耗时区间），生成的类型可能是元组也可能是 number[]，
 * 这里统一成元组 [下限, 上限]，由 endpoints.ts 的 jobsApi.estimate 转换。
 */
export type JobEstimate = Omit<Schemas["JobEstimate"], "est_seconds"> & { est_seconds: [number, number] }
export type JobProgress = Schemas["JobProgress"]
export type JobSummary = Schemas["JobSummary"]
export type JobLive = Schemas["JobLive"]
export type Job = Schemas["Job"]
export type JobSource = Schemas["JobSource"]
export type JobColumn = Schemas["JobColumn"]
export type JobPatch = Schemas["JobPatch"]
export type CategoryStat = Schemas["CategoryStat"]
export type Compression = Schemas["Compression"]
export type ItemSummary = Schemas["ItemSummary"]
export type ItemDetail = Schemas["ItemDetail"]
export type ItemPatch = Schemas["ItemPatch"]
export type AttemptLogEntry = Schemas["AttemptLogEntry"]
export type Track = Schemas["Track"]
export type CategoryList = Schemas["CategoryList"]

// SSE 和试运行的事件数据（04 第 10.1 节）：后端把这些模型登记进了 OpenAPI 的 components，直接取生成的类型，不手写。
// 全局流的 job.created、job.updated 是 JobSummary，单任务流的 job.updated 是 JobLive（见上）。
export type JobDeletedEvent = Schemas["JobDeletedEvent"]
export type ItemsUpdatedEvent = Schemas["ItemsUpdatedEvent"]
export type TracksUpdatedEvent = Schemas["TracksUpdatedEvent"]
export type PingEvent = Schemas["PingEvent"]
export type PlaygroundStageEvent = Schemas["PlaygroundStageEvent"]
/** 试运行的 delta 和 reasoning_delta 共用 */
export type PlaygroundDeltaEvent = Schemas["PlaygroundDeltaEvent"]
export type PlaygroundDone = Schemas["PlaygroundDone"]
export type PlaygroundErrorEvent = Schemas["PlaygroundErrorEvent"]

export type ErrorResponse = Schemas["ErrorResponse"]

export type TaskType = JobSummary["task_type"]
export type JobStatus = JobSummary["status"]
/** 暂停原因码（03 第 6.1 节）：界面按它决定提示和操作，不匹配中文文案 */
export type PauseReasonCode = NonNullable<JobSummary["status_reason_code"]>
export type ItemStatus = ItemSummary["status"]
export type TrackPhase = Track["phase"]
export type OutputMode = PromptTemplate["output_mode"]
export type JoinMode = JobSource["join_mode"]
export type ThemeSetting = Settings["theme"]
export type OpenMode = Settings["open_mode"]
export type RunMode = SystemInfo["run_mode"]
export type ItemOrder =
  | "seq"
  | "-seq"
  | "confidence"
  | "-confidence"
  | "latency_ms"
  | "-latency_ms"
  | "input_chars"
  | "-input_chars"

/** 结果表和导出共用的筛选条件（04 第 8.2 节） */
export interface ItemFilters {
  status?: ItemStatus[]
  label?: string[]
  q?: string
  reviewed?: boolean | null
  /** 意图或摘要有人工修正 */
  corrected?: boolean | null
}

export const TASK_TYPES: TaskType[] = ["classify", "summarize"]

export const TASK_TYPE_LABEL: Record<TaskType, string> = {
  classify: "意图识别",
  summarize: "文本摘要",
}

/** 任务中心表格里的短名 */
export const TASK_TYPE_SHORT: Record<TaskType, string> = {
  classify: "识别",
  summarize: "摘要",
}

export function isClassifyFieldMap(map: FieldMap): map is ClassifyFieldMap {
  return "label" in map
}

export function isSummarizeResult(value: ClassifyResult | SummarizeResult): value is SummarizeResult {
  return "summary" in value
}
