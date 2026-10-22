/** 上传文件：最近文件、上传、粘贴（04 第 7 节）。 */
import { defineStore } from "pinia"
import { ref } from "vue"
import { filesApi, uploadFile } from "@/api/endpoints"
import type { FileInfo } from "@/api/types"

/** 支持的扩展名（P0） */
export const SUPPORTED_EXTENSIONS = ["txt", "md", "csv", "xlsx", "xls"] as const

/** 选择文件对话框的 accept：只是方便筛选，是否支持仍由上传接口按扩展名判断 */
export const FILE_ACCEPT = SUPPORTED_EXTENSIONS.map((ext) => `.${ext}`).join(",")

/**
 * 拖入时能否从 MIME 判断“明显不支持”（06 第 6.11 节）：只有图片、音频、视频算。
 * 其他一律放行，交给上传接口按扩展名判断（不支持时返回 415）：Windows 上装了 Excel 时 .csv 的 MIME
 * 是 application/vnd.ms-excel，.md 常常为空，按白名单判断会误拒。
 */
export function isObviouslyUnsupported(mime: string): boolean {
  return /^(image|audio|video)\//i.test(mime)
}

export const useFilesStore = defineStore("files", () => {
  const recent = ref<FileInfo[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<unknown>(null)
  const cache = new Map<number, FileInfo>()
  /** 正在上传的文件名和进度（首页始发站、拖放层都显示它） */
  const uploadingName = ref<string | null>(null)
  const uploadProgress = ref<number | null>(null)

  function remember(file: FileInfo) {
    cache.set(file.id, file)
    recent.value = [file, ...recent.value.filter((f) => f.id !== file.id)].slice(0, 10)
  }

  async function load(force = false): Promise<void> {
    if (loaded.value && !force) return
    loading.value = true
    try {
      const page = await filesApi.list(0, 10)
      recent.value = page.items
      for (const f of page.items) cache.set(f.id, f)
      loaded.value = true
      error.value = null
    } catch (e) {
      error.value = e
      throw e
    } finally {
      loading.value = false
    }
  }

  async function get(id: number): Promise<FileInfo> {
    const hit = cache.get(id)
    if (hit) return hit
    const file = await filesApi.get(id)
    cache.set(id, file)
    return file
  }

  async function upload(file: File, onProgress?: (fraction: number) => void): Promise<FileInfo> {
    uploadingName.value = file.name
    uploadProgress.value = 0
    try {
      const info = await uploadFile(file, (fraction) => {
        uploadProgress.value = fraction
        onProgress?.(fraction)
      })
      remember(info)
      return info
    } finally {
      uploadingName.value = null
      uploadProgress.value = null
    }
  }

  async function paste(text: string, name?: string): Promise<FileInfo> {
    const info = await filesApi.paste(text, name)
    remember(info)
    return info
  }

  return { recent, loaded, loading, error, load, get, upload, paste, remember, uploadingName, uploadProgress }
})
