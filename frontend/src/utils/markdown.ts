/** 摘要可能含 Markdown：markdown-it 渲染后经 DOMPurify 清洗再输出（02 第 8.1 节）。 */
import DOMPurify from "dompurify"
import MarkdownIt from "markdown-it"

const md = new MarkdownIt({ html: false, linkify: false, breaks: true, typographer: false })

export function renderMarkdown(text: string | null | undefined): string {
  if (!text) return ""
  return DOMPurify.sanitize(md.render(text))
}
