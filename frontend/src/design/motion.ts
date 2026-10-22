/** 动效常量与“减少动态效果”判断（06 第 3.6、8 节）。 */

import { ref } from "vue"

/** 毫秒，与 tokens.css 的动效令牌一致 */
export const DUR = {
  press: 80,
  fast: 140,
  base: 220,
  slow: 360,
  line: 900,
  car: 160,
  number: 300,
  flash: 1200,
  pop: 220,
  stagger: 150,
  lightUp: 40,
  reorderGap: 2000,
} as const

export const EASE = {
  out: "cubic-bezier(0.16, 1, 0.3, 1)",
  in: "cubic-bezier(0.7, 0, 0.84, 0)",
  move: "cubic-bezier(0.65, 0, 0.35, 1)",
} as const

const query =
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null

/** 系统是否开启了“减少动态效果”（响应式） */
export const reducedMotion = ref<boolean>(query?.matches ?? false)

query?.addEventListener?.("change", (event: MediaQueryListEvent) => {
  reducedMotion.value = event.matches
})

/**
 * Web Animations API 的薄封装：减少动态效果时不播放。
 * 允许保留的短淡入淡出由调用方传 allowReduced=true，时长会压到 120 ms。
 */
export function animateEl(
  el: Element | null | undefined,
  keyframes: Keyframe[],
  options: KeyframeAnimationOptions,
  allowReduced = false,
): Animation | null {
  if (!el || typeof (el as HTMLElement).animate !== "function") return null
  if (reducedMotion.value) {
    if (!allowReduced) return null
    return el.animate(keyframes, { ...options, duration: Math.min(Number(options.duration ?? 120), 120), delay: 0 })
  }
  return el.animate(keyframes, options)
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void | Promise<void>) => { finished: Promise<void> }
}

/** 用 View Transitions 包住一次界面更新；不支持或减少动态效果时直接执行 */
export async function withViewTransition(update: () => void | Promise<void>): Promise<void> {
  const doc = document as ViewTransitionDocument
  if (reducedMotion.value || typeof doc.startViewTransition !== "function") {
    await update()
    return
  }
  try {
    const transition = doc.startViewTransition(update)
    await transition.finished
  } catch {
    // 过渡被打断时界面已经更新，不需要处理
  }
}
