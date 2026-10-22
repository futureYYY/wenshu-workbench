/**
 * 全部接口调用的封装（04）。组件和 store 只调用这里的函数。
 * 返回值都标注了 types.ts 里的类型：重新生成 schema.d.ts 后若有差异，类型检查会在这里指出。
 */
import { api, apiHeaders, apiUrl, ApiError, call, callVoid, errorFromResponse, networkError, toApiError } from "./client"
import type {
  CategoryList,
  FileInfo,
  FilePreview,
  Health,
  ItemDetail,
  ItemFilters,
  ItemOrder,
  ItemPatch,
  ItemSummary,
  Job,
  JobCreate,
  JobEstimate,
  JobPatch,
  JobStatus,
  JobSummary,
  ModelConfig,
  ModelConfigInput,
  ModelConfigPatch,
  ModelDraftRequest,
  ModelTestResult,
  PromptCopy,
  PromptInput,
  PromptTemplate,
  PromptVariable,
  PromptVersionDetail,
  PromptVersionSummary,
  RenderRequest,
  RenderResult,
  Settings,
  SettingsPatch,
  SystemInfo,
  TaskType,
  Track,
} from "./types"
import { filenameFromDisposition } from "@/utils/text"

export interface Page<T> {
  items: T[]
  total: number
}

function csv(list: readonly string[] | undefined): string | undefined {
  return list && list.length > 0 ? list.join(",") : undefined
}

function itemQuery(filters: ItemFilters) {
  return {
    status: csv(filters.status),
    label: filters.label && filters.label.length > 0 ? filters.label : undefined,
    q: filters.q && filters.q.trim() ? filters.q.trim() : undefined,
    reviewed: filters.reviewed ?? undefined,
    corrected: filters.corrected ?? undefined,
  }
}

// ---------------- 系统与设置 ----------------

export const systemApi = {
  health: (): Promise<Health> => call(api.GET("/api/health")),
  info: (): Promise<SystemInfo> => call(api.GET("/api/system/info")),
  openFolder: (target: "data" | "logs" | "exports"): Promise<void> =>
    callVoid(api.POST("/api/system/open-folder", { body: { target } })),
}

export const settingsApi = {
  get: (): Promise<Settings> => call(api.GET("/api/settings")),
  patch: (body: SettingsPatch): Promise<Settings> => call(api.PATCH("/api/settings", { body })),
}

// ---------------- 模型 ----------------

export const modelsApi = {
  /** 总是带上演示模型；是否显示由前端按设置 show_demo_model 决定 */
  list: async (): Promise<ModelConfig[]> =>
    (await call(api.GET("/api/models", { params: { query: { include_demo: true } } }))).items,
  get: (id: number): Promise<ModelConfig> => call(api.GET("/api/models/{id}", { params: { path: { id } } })),
  create: (body: ModelConfigInput): Promise<ModelConfig> => call(api.POST("/api/models", { body })),
  update: (id: number, body: ModelConfigPatch): Promise<ModelConfig> =>
    call(api.PATCH("/api/models/{id}", { params: { path: { id } }, body })),
  remove: (id: number): Promise<void> => callVoid(api.DELETE("/api/models/{id}", { params: { path: { id } } })),
  test: (id: number): Promise<ModelTestResult> =>
    call(api.POST("/api/models/{id}/test", { params: { path: { id } } })),
  testDraft: (body: ModelDraftRequest): Promise<ModelTestResult> =>
    call(api.POST("/api/models/test-draft", { body })),
  listRemote: async (body: ModelDraftRequest): Promise<string[]> =>
    (await call(api.POST("/api/models/list-remote", { body }))).models,
}

// ---------------- 提示词 ----------------

export const promptsApi = {
  list: async (taskType?: TaskType): Promise<PromptTemplate[]> =>
    (await call(api.GET("/api/prompts", { params: { query: { task_type: taskType ?? undefined } } }))).items,
  get: (id: number): Promise<PromptTemplate> => call(api.GET("/api/prompts/{id}", { params: { path: { id } } })),
  create: (body: PromptInput | PromptCopy): Promise<PromptTemplate> => call(api.POST("/api/prompts", { body })),
  save: (id: number, body: PromptInput): Promise<PromptTemplate> =>
    call(api.PUT("/api/prompts/{id}", { params: { path: { id } }, body })),
  remove: (id: number): Promise<void> => callVoid(api.DELETE("/api/prompts/{id}", { params: { path: { id } } })),
  versions: async (id: number): Promise<PromptVersionSummary[]> =>
    (await call(api.GET("/api/prompts/{id}/versions", { params: { path: { id } } }))).items,
  version: (id: number, version: number): Promise<PromptVersionDetail> =>
    call(api.GET("/api/prompts/{id}/versions/{version}", { params: { path: { id, version } } })),
  restore: (id: number, version: number): Promise<PromptTemplate> =>
    call(api.POST("/api/prompts/{id}/restore", { params: { path: { id } }, body: { version } })),
  resetBuiltin: (id: number): Promise<PromptTemplate> =>
    call(api.POST("/api/prompts/{id}/reset-builtin", { params: { path: { id } } })),
  variables: async (taskType: TaskType): Promise<PromptVariable[]> =>
    (await call(api.GET("/api/prompts/variables", { params: { query: { task_type: taskType } } }))).items,
  render: (body: RenderRequest): Promise<RenderResult> => call(api.POST("/api/prompts/render", { body })),
}

// ---------------- 文件 ----------------

export const filesApi = {
  list: (offset = 0, limit = 10): Promise<Page<FileInfo>> =>
    call(api.GET("/api/files", { params: { query: { offset, limit } } })),
  get: (id: number): Promise<FileInfo> => call(api.GET("/api/files/{id}", { params: { path: { id } } })),
  paste: (text: string, name?: string): Promise<FileInfo> =>
    call(api.POST("/api/files/paste", { body: { text, name: name || undefined } })),
  remove: (id: number): Promise<void> => callVoid(api.DELETE("/api/files/{id}", { params: { path: { id } } })),
  preview: (
    id: number,
    query: { sheet?: string | null; header_row?: number; offset?: number; limit?: number },
  ): Promise<FilePreview> =>
    call(
      api.GET("/api/files/{id}/preview", {
        params: {
          path: { id },
          query: {
            sheet: query.sheet ?? undefined,
            header_row: query.header_row,
            offset: query.offset,
            limit: query.limit,
          },
        },
      }),
    ),
}

/**
 * 上传文件（multipart，字段名 file）。用 XMLHttpRequest 以便拿到上传进度；
 * 内容与已有文件相同时后端返回 200 且 reused=true。
 */
export function uploadFile(file: File, onProgress?: (fraction: number) => void): Promise<FileInfo> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", apiUrl("/api/files"))
    for (const [key, value] of Object.entries(apiHeaders())) xhr.setRequestHeader(key, value)
    xhr.responseType = "text"
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total)
    }
    xhr.onerror = () => reject(networkError("upload"))
    xhr.onload = () => {
      let body: unknown
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined
      } catch {
        body = undefined
      }
      const response = new Response(null, { status: xhr.status })
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        onProgress?.(1)
        resolve(body as FileInfo)
      } else {
        reject(toApiError(response, body))
      }
    }
    const form = new FormData()
    form.append("file", file, file.name)
    xhr.send(form)
  })
}

// ---------------- 任务 ----------------

export interface JobListQuery {
  status?: JobStatus[]
  task_type?: TaskType | null
  q?: string
  offset?: number
  limit?: number
}

/** 预计耗时区间统一成元组 [下限, 上限]（生成的类型可能是 [number, number] 或 number[]） */
function secondsRange(value: readonly number[]): [number, number] {
  const lo = value[0] ?? 0
  return [lo, value[1] ?? lo]
}

export const jobsApi = {
  estimate: async (body: JobCreate): Promise<JobEstimate> => {
    const raw = await call(api.POST("/api/jobs/estimate", { body }))
    return { ...raw, est_seconds: secondsRange(raw.est_seconds) }
  },
  create: (body: JobCreate): Promise<Job> => call(api.POST("/api/jobs", { body })),
  list: (query: JobListQuery = {}): Promise<Page<JobSummary>> =>
    call(
      api.GET("/api/jobs", {
        params: {
          query: {
            status: csv(query.status),
            task_type: query.task_type ?? undefined,
            q: query.q && query.q.trim() ? query.q.trim() : undefined,
            offset: query.offset ?? 0,
            limit: query.limit ?? 50,
          },
        },
      }),
    ),
  get: (id: number): Promise<Job> => call(api.GET("/api/jobs/{id}", { params: { path: { id } } })),
  update: (id: number, body: JobPatch): Promise<Job> =>
    call(api.PATCH("/api/jobs/{id}", { params: { path: { id } }, body })),
  remove: (id: number): Promise<void> => callVoid(api.DELETE("/api/jobs/{id}", { params: { path: { id } } })),
  pause: (id: number): Promise<Job> => call(api.POST("/api/jobs/{id}/pause", { params: { path: { id } } })),
  resume: (id: number): Promise<Job> => call(api.POST("/api/jobs/{id}/resume", { params: { path: { id } } })),
  cancel: (id: number): Promise<Job> => call(api.POST("/api/jobs/{id}/cancel", { params: { path: { id } } })),
  retryFailed: (id: number): Promise<Job> =>
    call(api.POST("/api/jobs/{id}/retry-failed", { params: { path: { id } } })),
  categories: (id: number): Promise<CategoryList> =>
    call(api.GET("/api/jobs/{id}/categories", { params: { path: { id } } })),
  tracks: async (id: number): Promise<Track[]> =>
    (await call(api.GET("/api/jobs/{id}/tracks", { params: { path: { id } } }))).items,
}

export const itemsApi = {
  list: (
    jobId: number,
    filters: ItemFilters,
    order: ItemOrder = "seq",
    offset = 0,
    limit = 200,
  ): Promise<Page<ItemSummary>> =>
    call(
      api.GET("/api/jobs/{id}/items", {
        params: { path: { id: jobId }, query: { ...itemQuery(filters), order, offset, limit } },
      }),
    ),
  get: (jobId: number, itemId: number): Promise<ItemDetail> =>
    call(api.GET("/api/jobs/{id}/items/{item_id}", { params: { path: { id: jobId, item_id: itemId } } })),
  update: (jobId: number, itemId: number, body: ItemPatch): Promise<ItemSummary> =>
    call(
      api.PATCH("/api/jobs/{id}/items/{item_id}", { params: { path: { id: jobId, item_id: itemId } }, body }),
    ),
  rerun: (jobId: number, itemId: number): Promise<ItemSummary> =>
    call(
      api.POST("/api/jobs/{id}/items/{item_id}/rerun", { params: { path: { id: jobId, item_id: itemId } } }),
    ),
}

export type ExportFormat = "xlsx" | "csv"
export type ExportScope = "all" | "filtered"

/** 下载导出文件，返回文件内容和后端给的文件名 */
export async function exportJob(
  jobId: number,
  format: ExportFormat,
  scope: ExportScope,
  filters: ItemFilters,
): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams({ format, scope })
  if (scope === "filtered") {
    const q = itemQuery(filters)
    if (q.status) params.set("status", q.status)
    for (const label of q.label ?? []) params.append("label", label)
    if (q.q) params.set("q", q.q)
    if (q.reviewed !== undefined) params.set("reviewed", String(q.reviewed))
    if (q.corrected !== undefined) params.set("corrected", String(q.corrected))
  }
  let response: Response
  try {
    response = await fetch(apiUrl(`/api/jobs/${jobId}/export?${params.toString()}`))
  } catch (e) {
    throw networkError(e)
  }
  if (!response.ok) throw await errorFromResponse(response)
  const filename =
    filenameFromDisposition(response.headers.get("Content-Disposition")) ?? `文枢导出_${jobId}.${format}`
  const blob = await response.blob()
  return { blob, filename }
}

export { ApiError }
