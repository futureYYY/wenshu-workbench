/** 错误码到中文建议的映射（05 第 6.1 节的 error_code）。 */

const SUGGESTIONS: Record<string, string> = {
  PARSE_ERROR: "检查提示词的输出格式要求，或在原始输出里看模型实际返回了什么。",
  OUTPUT_TRUNCATED: "调大模型或提示词的最大输出 tokens 后重新处理。",
  TIMEOUT: "检查网络和模型服务是否正常，或在模型设置里调大超时。",
  CONNECTION_ERROR: "检查接口地址、网络和代理设置是否正确。",
  RATE_LIMITED: "降低并发，或稍后重试失败项。",
  SERVER_ERROR: "模型服务暂时不可用，稍后重试失败项。",
  EMPTY_OUTPUT: "会思考的模型可能需要更大的最大输出，或在模型的额外请求体里关闭思考。",
  CONTEXT_TOO_LONG: "在模型设置里填写正确的上下文长度，或缩短原文后重新处理。",
  CONTEXT_TOO_SMALL: "在模型设置里调大上下文长度，或调小最大输出。",
  BAD_REQUEST: "检查模型名和额外请求体参数是否被接口支持。",
  AUTH_FAILED: "去修改模型的 API Key，然后继续任务。",
  MODEL_NOT_FOUND: "检查模型名和接口地址，然后继续任务。",
  INTERNAL_ERROR: "打开日志目录查看 app.log 了解详情。",
}

/** 某个错误码的下一步建议；不认识时返回空字符串 */
export function suggestionFor(code: string | null | undefined): string {
  if (!code) return ""
  return SUGGESTIONS[code] ?? ""
}

/** 失败条目顶部的一句话：发生了什么 + 原因 + 下一步 */
export function failureSentence(code: string | null | undefined, message: string | null | undefined): string {
  const what = (message ?? "").trim() || "处理失败"
  const end = /[。.！!？?]$/.test(what) ? "" : "。"
  const next = suggestionFor(code)
  return next ? `${what}${end}${next}` : `${what}${end}`
}
