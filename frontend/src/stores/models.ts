/** 模型配置（04 第 4 节）。 */
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { modelsApi } from "@/api/endpoints"
import type { ModelConfig, TaskType } from "@/api/types"
import { useSettingsStore } from "./settings"

/** 后端首次启动生成的“默认自定义模型”占位条目的地址 */
export const PLACEHOLDER_BASE_URL = "https://api.example.com/v1"

export function isDemoModel(model: ModelConfig | null | undefined): boolean {
  return model?.provider_kind === "demo"
}

/** 占位条目：不是演示模型、地址是占位地址、没有密钥 */
export function isPlaceholderModel(model: ModelConfig | null | undefined): boolean {
  return !!model && model.provider_kind !== "demo" && model.base_url === PLACEHOLDER_BASE_URL && !model.has_api_key
}

/** 地址的主机部分，用于列表显示 */
export function modelHost(model: ModelConfig): string {
  if (model.provider_kind === "demo") return "本机模拟"
  try {
    return new URL(model.base_url).host
  } catch {
    return model.base_url
  }
}

export const useModelsStore = defineStore("models", () => {
  const items = ref<ModelConfig[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<unknown>(null)
  const settingsStore = useSettingsStore()

  async function load(force = false): Promise<void> {
    if (loaded.value && !force) return
    loading.value = true
    try {
      items.value = await modelsApi.list()
      loaded.value = true
      error.value = null
    } catch (e) {
      error.value = e
      throw e
    } finally {
      loading.value = false
    }
  }

  /** 按设置决定是否显示演示模型 */
  const visible = computed(() =>
    items.value.filter((m) => m.provider_kind !== "demo" || settingsStore.settings?.show_demo_model !== false),
  )

  const realModels = computed(() => items.value.filter((m) => m.provider_kind !== "demo"))
  const placeholder = computed(() => items.value.find((m) => isPlaceholderModel(m)) ?? null)
  const demo = computed(() => items.value.find((m) => m.provider_kind === "demo") ?? null)

  function byId(id: number | null | undefined): ModelConfig | null {
    if (id === null || id === undefined) return null
    return items.value.find((m) => m.id === id) ?? null
  }

  function defaultFor(task: TaskType): ModelConfig | null {
    return byId(settingsStore.defaultModelId(task))
  }

  function upsert(model: ModelConfig) {
    const index = items.value.findIndex((m) => m.id === model.id)
    if (index >= 0) items.value.splice(index, 1, model)
    else items.value.push(model)
  }

  function remove(id: number) {
    items.value = items.value.filter((m) => m.id !== id)
  }

  /** “接入真实模型”的去处：有占位条目时编辑它，否则新建 */
  const connectRealModelRoute = computed(() =>
    placeholder.value ? { path: "/models", query: { edit: String(placeholder.value.id) } } : { path: "/models", query: { new: "1" } },
  )

  return {
    items,
    loaded,
    loading,
    error,
    load,
    visible,
    realModels,
    placeholder,
    demo,
    byId,
    defaultFor,
    upsert,
    remove,
    connectRealModelRoute,
  }
})
