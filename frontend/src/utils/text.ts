/** 文本相关的小工具。 */

// 与后端 05 第 7.1 节相同的 CJK 字符范围，用于估算 tokens
const CJK = /[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]/g

/** 不依赖分词器的 tokens 估算，与后端公式一致 */
export function estimateTokens(text: string): number {
  if (!text) return 0
  const cjk = text.match(CJK)?.length ?? 0
  return Math.ceil(cjk * 1.0 + (text.length - cjk) / 3.5)
}

/** 把换行替换成空格，变成单行预览 */
export function singleLine(text: string | null | undefined): string {
  return (text ?? "").replace(/[\r\n]+/g, " ").trim()
}

/** 截断到指定字数，末尾加省略号 */
export function clip(text: string | null | undefined, max: number): string {
  const s = text ?? ""
  return s.length > max ? `${s.slice(0, max)}…` : s
}

/** 截断时从发送内容里取出“中间省略 N 字”的 N */
export function extractOmittedChars(text: string | null | undefined): number | null {
  const m = /（中间省略 (\d+) 字）/.exec(text ?? "")
  return m ? Number(m[1]) : null
}

export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * 模糊匹配：按顺序出现的字符都在文本里就算匹配，返回得分（越大越好），不匹配返回 -1。
 * 连续命中、命中开头加分。
 */
export function fuzzyScore(query: string, text: string): number {
  const q = query.trim().toLowerCase()
  if (!q) return 0
  const t = text.toLowerCase()
  const direct = t.indexOf(q)
  if (direct >= 0) return 1000 - direct * 2 - (t.length - q.length) * 0.1
  let score = 0
  let ti = 0
  let streak = 0
  for (const ch of q) {
    const found = t.indexOf(ch, ti)
    if (found < 0) return -1
    streak = found === ti ? streak + 1 : 0
    score += 10 + streak * 5 - (found - ti)
    ti = found + 1
  }
  return score
}

/** 变量匹配规则，与后端 05 第 2.3 节一致 */
export const VARIABLE_PATTERN = /\{\{\s*(col:[^{}]+?|[a-z_]+)\s*\}\}/g

/** 列出文本里引用到的变量名（去重，保持出现顺序） */
export function listVariables(text: string): string[] {
  const out: string[] = []
  for (const m of text.matchAll(VARIABLE_PATTERN)) {
    const name = (m[1] ?? "").trim()
    if (name && !out.includes(name)) out.push(name)
  }
  return out
}

/** 文件名去掉扩展名 */
export function stripExtension(name: string): string {
  const i = name.lastIndexOf(".")
  return i > 0 ? name.slice(0, i) : name
}

/** 从 Content-Disposition 里取文件名（支持 filename*=UTF-8''…） */
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*\s*=\s*([^']*)''([^;]+)/i.exec(header)
  if (star && star[2]) {
    try {
      return decodeURIComponent(star[2].trim().replace(/^"|"$/g, ""))
    } catch {
      return star[2]
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header)
  return plain && plain[1] ? plain[1].trim() : null
}
