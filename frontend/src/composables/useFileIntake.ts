/**
 * 接收文件或粘贴文本，开始一次新任务：上传 → 进入 /new?file={id} 的“选数据”站（06 第 6.1、6.11 节）。
 * 首页始发站、拖放层、新建任务第一站、命令面板共用。
 */
import { onBeforeUnmount, onMounted } from "vue"
import { useRouter } from "vue-router"
import type { FileInfo } from "@/api/types"
import { withViewTransition } from "@/design/motion"
import { useFilesStore } from "@/stores/files"
import { useNewJobStore } from "@/stores/newJob"
import { useSettingsStore } from "@/stores/settings"
import { isTypingTarget } from "@/utils/keyboard"
import { notify, notifyError } from "@/utils/toast"

export const UNSUPPORTED_MESSAGE = "不支持这种文件，支持 txt、md、csv、xlsx、xls"

export function useFileIntake() {
  const files = useFilesStore()
  const newJob = useNewJobStore()
  const settings = useSettingsStore()
  const router = useRouter()

  async function go(info: FileInfo) {
    if (info.reused) notify("这个文件之前上传过，已直接使用已有记录")
    newJob.reset()
    const loading = newJob.selectFile(info)
    await withViewTransition(async () => {
      await router.push({ path: "/new", query: { file: String(info.id) } })
    })
    await loading
  }

  /**
   * 上传一个文件并进入“选数据”站；返回是否成功。
   * 文件类型不在这里判断：交给上传接口按扩展名判断，不支持时返回 415，toast 显示它的说明（06 第 6.11 节）。
   */
  async function intakeFile(file: File): Promise<boolean> {
    const limit = settings.limits.max_upload_bytes
    if (file.size > limit) {
      notify("文件超过 50 MB，请拆分后再上传")
      return false
    }
    try {
      const info = await files.upload(file)
      await go(info)
      return true
    } catch (e) {
      notifyError(e)
      return false
    }
  }

  /** 把粘贴的文本存成一个文件并进入“选数据”站 */
  async function intakeText(text: string, name?: string): Promise<boolean> {
    if (!text.trim()) {
      notify("粘贴的内容是空的")
      return false
    }
    try {
      const info = await files.paste(text, name)
      await go(info)
      return true
    } catch (e) {
      notifyError(e)
      return false
    }
  }

  return { intakeFile, intakeText }
}

/**
 * 焦点不在输入框时按 Ctrl+V：直接把剪贴板文本作为“粘贴文本”开始（06 第 6.11 节）。
 * 在首页和新建任务第一站使用；enabled 返回 false 时不处理。
 */
export function usePasteToStart(enabled: () => boolean = () => true) {
  const { intakeText } = useFileIntake()

  function onPaste(event: ClipboardEvent) {
    if (!enabled() || isTypingTarget(event.target) || isTypingTarget(document.activeElement)) return
    const text = event.clipboardData?.getData("text/plain") ?? ""
    if (!text.trim()) return
    event.preventDefault()
    void intakeText(text)
  }

  onMounted(() => window.addEventListener("paste", onPaste))
  onBeforeUnmount(() => window.removeEventListener("paste", onPaste))
}
