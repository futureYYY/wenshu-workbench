/** 设置与系统信息（04 第 3 节）。 */
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { settingsApi, systemApi } from "@/api/endpoints"
import type { Settings, SettingsPatch, SystemInfo, TaskType } from "@/api/types"

export const useSettingsStore = defineStore("settings", () => {
  const settings = ref<Settings | null>(null)
  const info = ref<SystemInfo | null>(null)
  const loaded = ref(false)
  const error = ref<unknown>(null)
  let pending: Promise<void> | null = null

  async function load(force = false): Promise<void> {
    if (loaded.value && !force) return
    if (pending) return pending
    pending = (async () => {
      try {
        const [s, i] = await Promise.all([settingsApi.get(), systemApi.info()])
        settings.value = s
        info.value = i
        loaded.value = true
        error.value = null
      } catch (e) {
        error.value = e
        throw e
      } finally {
        pending = null
      }
    })()
    return pending
  }

  async function patch(body: SettingsPatch): Promise<Settings> {
    const next = await settingsApi.patch(body)
    settings.value = next
    return next
  }

  const limits = computed(
    () => settings.value?.limits ?? { max_concurrency: 20, max_rows_per_source: 100_000, max_upload_bytes: 52_428_800 },
  )

  function defaultConcurrency(task: TaskType): number {
    return settings.value?.default_concurrency[task] ?? 5
  }

  function defaultModelId(task: TaskType): number | null {
    return settings.value?.default_model_id[task] ?? null
  }

  function defaultPromptId(task: TaskType): number | null {
    return settings.value?.default_prompt_id[task] ?? null
  }

  return { settings, info, loaded, error, load, patch, limits, defaultConcurrency, defaultModelId, defaultPromptId }
})
