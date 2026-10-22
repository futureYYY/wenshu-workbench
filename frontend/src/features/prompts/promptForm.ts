/** 提示词编辑表单与接口模型之间的转换（04 第 5 节）。 */
import type { OutputMode, PromptDraft, PromptInput, PromptSnapshot, PromptTemplate, TaskType } from "@/api/types"
import { isClassifyFieldMap } from "@/api/types"

export interface PromptForm {
  name: string
  description: string
  system_prompt: string
  user_template: string
  chunk_template: string
  merge_template: string
  output_mode: OutputMode
  classify_map: { label: string; confidence: string; reason: string }
  summarize_map: { summary: string; key_points: string }
  temperature: number | null
  max_output_tokens: number | null
}

export const DEFAULT_CLASSIFY_MAP = { label: "intent", confidence: "confidence", reason: "reason" }
export const DEFAULT_SUMMARIZE_MAP = { summary: "summary", key_points: "key_points" }

type Source = Pick<
  PromptTemplate,
  | "name"
  | "system_prompt"
  | "user_template"
  | "chunk_template"
  | "merge_template"
  | "output_mode"
  | "field_map"
  | "temperature"
  | "max_output_tokens"
> & { description?: string }

export function formFrom(source: Source | PromptSnapshot): PromptForm {
  const map = source.field_map
  return {
    name: source.name,
    description: "description" in source ? (source.description ?? "") : "",
    system_prompt: source.system_prompt,
    user_template: source.user_template,
    chunk_template: source.chunk_template ?? "",
    merge_template: source.merge_template ?? "",
    output_mode: source.output_mode,
    classify_map: isClassifyFieldMap(map)
      ? { label: map.label, confidence: map.confidence ?? "", reason: map.reason ?? "" }
      : { ...DEFAULT_CLASSIFY_MAP },
    summarize_map: !isClassifyFieldMap(map)
      ? { summary: map.summary, key_points: map.key_points ?? "" }
      : { ...DEFAULT_SUMMARIZE_MAP },
    temperature: source.temperature,
    max_output_tokens: source.max_output_tokens,
  }
}

export function toDraft(form: PromptForm, taskType: TaskType): PromptDraft {
  const field_map =
    taskType === "classify"
      ? {
          label: form.classify_map.label.trim(),
          confidence: form.classify_map.confidence.trim() || null,
          reason: form.classify_map.reason.trim() || null,
        }
      : { summary: form.summarize_map.summary.trim(), key_points: form.summarize_map.key_points.trim() || null }
  return {
    task_type: taskType,
    system_prompt: form.system_prompt,
    user_template: form.user_template,
    chunk_template: taskType === "summarize" ? form.chunk_template : null,
    merge_template: taskType === "summarize" ? form.merge_template : null,
    output_mode: form.output_mode,
    field_map,
    temperature: form.temperature,
    max_output_tokens: form.max_output_tokens,
  }
}

export function toInput(form: PromptForm, taskType: TaskType, note: string): PromptInput {
  return {
    ...toDraft(form, taskType),
    name: form.name.trim(),
    description: form.description.trim(),
    note: note.trim(),
  }
}

/** 只比较会被保存的内容 */
export function sameForm(a: PromptForm | null, b: PromptForm | null, taskType: TaskType): boolean {
  if (!a || !b) return a === b
  const x = { ...toDraft(a, taskType), name: a.name.trim(), description: a.description.trim() }
  const y = { ...toDraft(b, taskType), name: b.name.trim(), description: b.description.trim() }
  return JSON.stringify(x) === JSON.stringify(y)
}

/** 折叠标题行显示的当前取值摘要 */
export function outputSummary(form: PromptForm, taskType: TaskType): string {
  if (form.output_mode === "text") return "纯文本"
  if (taskType === "classify") {
    const m = form.classify_map
    return `JSON  ${[m.label, m.confidence, m.reason].filter(Boolean).join(" / ")}`
  }
  const m = form.summarize_map
  return `JSON  ${[m.summary, m.key_points].filter(Boolean).join(" / ")}`
}

export function paramsSummary(form: PromptForm): string {
  const parts: string[] = []
  parts.push(form.temperature === null ? "温度 按模型" : `温度 ${form.temperature}`)
  parts.push(form.max_output_tokens === null ? "最大输出 按模型" : `最大输出 ${form.max_output_tokens}`)
  return parts.join("   ")
}
