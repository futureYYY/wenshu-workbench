/**
 * 试运行的 POST 流（04 第 6 节）。EventSource 不支持 POST，这里用 fetch 读取 ReadableStream，
 * 按 SSE 格式解析；调用方用 AbortController 中途停止，服务端会随之取消上游请求。
 */
import { ApiError, apiHeaders, apiUrl, errorFromResponse, isAbortError, networkError } from "./client"
import type {
  PlaygroundDeltaEvent,
  PlaygroundDone,
  PlaygroundErrorEvent,
  PlaygroundRunRequest,
  PlaygroundStageEvent,
} from "./types"
import { SseParser, type SseMessage } from "@/utils/sse"

export interface PlaygroundHandlers {
  onStage?: (stage: PlaygroundStageEvent) => void
  onDelta?: (delta: PlaygroundDeltaEvent) => void
  onReasoningDelta?: (delta: PlaygroundDeltaEvent) => void
  onDone?: (done: PlaygroundDone) => void
  onError?: (error: PlaygroundErrorEvent) => void
}

function dispatch(message: SseMessage, handlers: PlaygroundHandlers): void {
  let data: unknown
  try {
    data = message.data ? JSON.parse(message.data) : {}
  } catch {
    return
  }
  switch (message.event) {
    case "stage":
      handlers.onStage?.(data as PlaygroundStageEvent)
      break
    case "delta":
      handlers.onDelta?.(data as PlaygroundDeltaEvent)
      break
    case "reasoning_delta":
      handlers.onReasoningDelta?.(data as PlaygroundDeltaEvent)
      break
    case "done":
      handlers.onDone?.(data as PlaygroundDone)
      break
    case "error":
      handlers.onError?.(data as PlaygroundErrorEvent)
      break
    default:
      break
  }
}

/**
 * 运行一次试运行。正常结束或被中止时 resolve；请求本身失败（例如 422 校验错误）时抛出 ApiError。
 * 模型调用失败不抛异常，而是通过 onError 事件告知。
 */
export async function runPlayground(
  body: PlaygroundRunRequest,
  handlers: PlaygroundHandlers,
  signal: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(apiUrl("/api/playground/run"), {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
      body: JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if (isAbortError(e) || signal.aborted) return
    throw networkError(e)
  }
  if (!response.ok) throw await errorFromResponse(response)
  if (!response.body) throw new ApiError(response.status, "EMPTY_STREAM", "试运行没有返回内容")

  const reader = response.body.getReader()
  const decoder = new TextDecoder("utf-8")
  const parser = new SseParser()
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      for (const message of parser.feed(decoder.decode(value, { stream: true }))) dispatch(message, handlers)
    }
    for (const message of parser.feed(decoder.decode())) dispatch(message, handlers)
    for (const message of parser.flush()) dispatch(message, handlers)
  } catch (e) {
    if (isAbortError(e) || signal.aborted) return
    throw networkError(e)
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // 读取被中止时锁可能已经释放
    }
  }
}
