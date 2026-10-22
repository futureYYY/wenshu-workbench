/** 在 App.vue 里建立全局 SSE 连接，更新任务 store 和连接状态（02 第 8.3 节）。 */
import { onBeforeUnmount, onMounted } from "vue"
import { openEventStream } from "@/api/events"
import { useJobsStore } from "@/stores/jobs"
import { useUiStore } from "@/stores/ui"

export function useGlobalEvents(): void {
  const jobs = useJobsStore()
  const ui = useUiStore()
  let close: (() => void) | null = null

  onMounted(() => {
    close = openEventStream({
      onEvent: (name, data) => jobs.applyEvent(name, data),
      onStateChange: (state) => {
        ui.connection = state
      },
      onReconnected: () => {
        // 服务端不做断线补发：重连后重新拉取
        void jobs.load().catch(() => undefined)
      },
    })
  })

  onBeforeUnmount(() => {
    close?.()
    close = null
  })
}
