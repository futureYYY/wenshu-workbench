/**
 * openapi-fetch 客户端与统一错误处理（02 第 8.2 节）。
 * - 接口地址由构建变量 VITE_API_BASE 决定，默认为空（同源）；
 * - 所有非 GET 请求都带 X-WenShu-Client: 1（后端据此拒绝其他网页的跨站调用）；
 * - 错误响应统一转成 ApiError（code、message），由调用处决定是 toast 还是表单内提示。
 */
import createClient, { type Middleware } from "openapi-fetch"
import type { paths } from "./schema"

export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "")

/** 不经过 openapi-fetch 的请求（SSE、上传、试运行流、导出）也用它拼地址 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

/** 不经过 openapi-fetch 的非 GET 请求必须带的请求头 */
export function apiHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return { "X-WenShu-Client": "1", ...extra }
}

export interface FieldError {
  path: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: Record<string, unknown>

  constructor(status: number, code: string, message: string, detail: Record<string, unknown> = {}) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.detail = detail
  }

  /** VALIDATION_ERROR 的逐字段说明 */
  get fields(): FieldError[] {
    const raw = this.detail.fields
    if (!Array.isArray(raw)) return []
    return raw
      .filter((f): f is { path: unknown; message: unknown } => typeof f === "object" && f !== null)
      .map((f) => ({ path: String(f.path ?? ""), message: String(f.message ?? "") }))
  }

  /** 某个字段的说明（表单内提示用） */
  fieldMessage(path: string): string | null {
    return this.fields.find((f) => f.path === path)?.message ?? null
  }
}

export const NETWORK_ERROR_MESSAGE = "连不上文枢后端。请确认文枢仍在运行（任务栏右下角的托盘图标），然后重试。"

export function networkError(cause?: unknown): ApiError {
  return new ApiError(0, "NETWORK_ERROR", NETWORK_ERROR_MESSAGE, { cause: String(cause ?? "") })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function defaultMessage(status: number): string {
  if (status === 404) return "要找的内容不存在，可能已被删除"
  if (status === 413) return "文件超过 50 MB，请拆分后再上传"
  if (status >= 500) return "文枢后端出错了，详情见日志目录里的 app.log"
  return `请求没有完成（HTTP ${status}）`
}

/** 把后端的错误体 {error: {code, message, detail}} 转成 ApiError */
export function toApiError(response: Response, body: unknown): ApiError {
  const err = isRecord(body) && isRecord(body.error) ? body.error : null
  if (err && typeof err.code === "string" && typeof err.message === "string") {
    return new ApiError(response.status, err.code, err.message, isRecord(err.detail) ? err.detail : {})
  }
  return new ApiError(response.status, `HTTP_${response.status}`, defaultMessage(response.status))
}

/** 从原始 Response 读取错误体 */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await response.clone().json()
  } catch {
    body = undefined
  }
  return toApiError(response, body)
}

const clientHeader: Middleware = {
  onRequest({ request }) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      request.headers.set("X-WenShu-Client", "1")
    }
    return request
  },
}

export const api = createClient<paths>({ baseUrl: API_BASE })
api.use(clientHeader)

interface ApiResult<D> {
  data?: D
  error?: unknown
  response: Response
}

/** 等待 openapi-fetch 的调用，成功返回数据，失败抛出 ApiError */
export async function call<D>(promise: Promise<ApiResult<D>>): Promise<NonNullable<D>> {
  let result: ApiResult<D>
  try {
    result = await promise
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw networkError(e)
  }
  if (!result.response.ok || result.data === undefined || result.data === null) {
    throw toApiError(result.response, result.error)
  }
  return result.data as NonNullable<D>
}

/** 没有响应体的调用（204） */
export async function callVoid(promise: Promise<{ error?: unknown; response: Response }>): Promise<void> {
  let result: { error?: unknown; response: Response }
  try {
    result = await promise
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw networkError(e)
  }
  if (!result.response.ok) throw toApiError(result.response, result.error)
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError"
}
