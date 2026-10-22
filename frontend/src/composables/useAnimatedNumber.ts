/** 数字滚动过渡（300 ms，06 第 7.7 节）；减少动态效果时直接更新。 */
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue"
import { DUR, reducedMotion } from "@/design/motion"

/**
 * @param source 目标值
 * @param duration 过渡时长
 * @param start 初始显示值；给了就在挂载后从它滚到目标值（新线路的计数从 0 滚到实际值）
 * @param delay 初次滚动前的等待（与“开通新线路”的动画对齐）
 */
export function useAnimatedNumber(
  source: () => number,
  duration: number = DUR.number,
  start?: number,
  delay = 0,
): Ref<number> {
  const display = ref(start ?? source())
  let frame: number | null = null
  let timer: number | undefined

  function stop() {
    if (frame !== null) cancelAnimationFrame(frame)
    frame = null
  }

  function animateTo(to: number) {
    stop()
    const from = display.value
    if (reducedMotion.value || typeof requestAnimationFrame !== "function" || from === to || !Number.isFinite(to)) {
      display.value = to
      return
    }
    const begin = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - begin) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      display.value = from + (to - from) * eased
      if (t < 1) frame = requestAnimationFrame(tick)
      else {
        display.value = to
        frame = null
      }
    }
    frame = requestAnimationFrame(tick)
  }

  watch(source, (to) => animateTo(to))

  onMounted(() => {
    if (start === undefined) return
    if (delay > 0 && !reducedMotion.value) timer = window.setTimeout(() => animateTo(source()), delay)
    else animateTo(source())
  })

  onBeforeUnmount(() => {
    stop()
    window.clearTimeout(timer)
  })
  return display
}
