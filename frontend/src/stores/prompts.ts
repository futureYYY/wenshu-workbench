/** 提示词模板与变量清单（04 第 5 节）。 */
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { promptsApi } from "@/api/endpoints"
import type { PromptTemplate, PromptVariable, TaskType } from "@/api/types"

export const usePromptsStore = defineStore("prompts", () => {
  const items = ref<PromptTemplate[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<unknown>(null)
  const variables = ref<Partial<Record<TaskType, PromptVariable[]>>>({})

  async function load(force = false): Promise<void> {
    if (loaded.value && !force) return
    loading.value = true
    try {
      items.value = await promptsApi.list()
      loaded.value = true
      error.value = null
    } catch (e) {
      error.value = e
      throw e
    } finally {
      loading.value = false
    }
  }

  function byType(task: TaskType): PromptTemplate[] {
    // 后端已按“默认、内置、修改时间倒序”排好
    return items.value.filter((p) => p.task_type === task)
  }

  const classify = computed(() => byType("classify"))
  const summarize = computed(() => byType("summarize"))

  function byId(id: number | null | undefined): PromptTemplate | null {
    if (id === null || id === undefined) return null
    return items.value.find((p) => p.id === id) ?? null
  }

  function defaultFor(task: TaskType): PromptTemplate | null {
    return items.value.find((p) => p.task_type === task && p.is_default) ?? byType(task)[0] ?? null
  }

  function upsert(prompt: PromptTemplate) {
    const index = items.value.findIndex((p) => p.id === prompt.id)
    if (index >= 0) items.value.splice(index, 1, prompt)
    else items.value.push(prompt)
  }

  function remove(id: number) {
    items.value = items.value.filter((p) => p.id !== id)
  }

  /** 把某个模板设为默认后，本地同步 is_default 标记 */
  function markDefault(task: TaskType, id: number) {
    items.value = items.value.map((p) => (p.task_type === task ? { ...p, is_default: p.id === id } : p))
  }

  async function loadVariables(task: TaskType): Promise<PromptVariable[]> {
    const cached = variables.value[task]
    if (cached) return cached
    const list = await promptsApi.variables(task)
    variables.value = { ...variables.value, [task]: list }
    return list
  }

  return {
    items,
    loaded,
    loading,
    error,
    load,
    byType,
    classify,
    summarize,
    byId,
    defaultFor,
    upsert,
    remove,
    markDefault,
    variables,
    loadVariables,
  }
})
