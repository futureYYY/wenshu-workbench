<script setup lang="ts">
// 外壳（06 第 4 节）：左侧导航栏 + 内容区；内容区顶部是页面栏。全局浮层（命令面板、toast、拖放层）挂在这里。
import { Cpu, House, Info, ListChecks, MessageSquareText, Moon, Search, Settings as SettingsIcon, Sun, SunMoon } from "@lucide/vue"
import { TooltipProvider } from "reka-ui"
import { computed, nextTick, onBeforeUnmount, onMounted, watch, type Component } from "vue"
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router"
import { Toaster } from "vue-sonner"
import Kbd from "@/components/base/Kbd.vue"
import Logo from "@/components/base/Logo.vue"
import Tooltip from "@/components/base/Tooltip.vue"
import { useGlobalEvents } from "@/composables/useGlobalEvents"
import { useShortcut } from "@/composables/useShortcuts"
import CommandPalette from "@/features/command-palette/CommandPalette.vue"
import ShortcutsDialog from "@/features/command-palette/ShortcutsDialog.vue"
import DropOverlay from "@/features/drop-overlay/DropOverlay.vue"
import { useJobsStore } from "@/stores/jobs"
import { useModelsStore } from "@/stores/models"
import { useNewJobStore } from "@/stores/newJob"
import { usePromptsStore } from "@/stores/prompts"
import { useSettingsStore } from "@/stores/settings"
import { isOverlayOpen, useUiStore } from "@/stores/ui"
import { notifyError } from "@/utils/toast"

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const jobs = useJobsStore()
const settingsStore = useSettingsStore()
const models = useModelsStore()
const prompts = usePromptsStore()
const newJob = useNewJobStore()

useGlobalEvents()

interface NavItem {
  key: "home" | "jobs" | "prompts" | "models" | "settings" | "about"
  label: string
  to: string
  icon: Component
}

const NAV: NavItem[] = [
  { key: "home", label: "首页", to: "/", icon: House },
  { key: "jobs", label: "任务", to: "/jobs", icon: ListChecks },
  { key: "prompts", label: "提示词", to: "/prompts", icon: MessageSquareText },
  { key: "models", label: "模型", to: "/models", icon: Cpu },
  { key: "settings", label: "设置", to: "/settings", icon: SettingsIcon },
  { key: "about", label: "关于", to: "/about", icon: Info },
]

const activeNav = computed(() => route.meta.nav ?? null)
const pageTitle = computed(() => route.meta.title ?? "")
const hasRunning = computed(() => jobs.running.length > 0)

const themeIcon = computed(() => {
  if (ui.themeSetting === "system") return SunMoon
  return ui.resolvedTheme === "dark" ? Moon : Sun
})
const themeLabel = computed(() => (ui.resolvedTheme === "dark" ? "切换到亮色" : "切换到暗色"))

async function toggleTheme() {
  const next = ui.toggleTheme()
  try {
    await settingsStore.patch({ theme: next })
  } catch (e) {
    notifyError(e)
  }
}

function openPalette() {
  ui.paletteOpen = true
}

// ---- 全局快捷键（06 第 7.3 节） ----
useShortcut("ctrl+k", () => {
  ui.paletteOpen = !ui.paletteOpen
})
useShortcut("ctrl+n", () => {
  if (route.name !== "new-job") newJob.reset()
  void router.push("/new")
})
useShortcut("ctrl+,", () => void router.push("/settings"))
useShortcut("ctrl+shift+l", () => void toggleTheme())
useShortcut("?", () => {
  ui.shortcutsOpen = true
})
useShortcut(
  "escape",
  () => {
    // 没有浮层时清除当前页面的筛选
    if (isOverlayOpen()) return false
    return ui.clearFilterHandler ? ui.clearFilterHandler() : false
  },
  { preventDefault: false },
)

// ---- 窗口标题（06 第 7.8 节） ----
watch(
  () => jobs.running.map((j) => `${j.id}:${Math.floor(j.progress.percent)}`).join("|"),
  () => {
    const list = jobs.running
    if (list.length === 0) document.title = "文枢"
    else if (list.length === 1) document.title = `(${Math.floor(list[0]?.progress.percent ?? 0)}%) 文枢`
    else document.title = `(${list.length} 个运行中) 文枢`
  },
  { immediate: true },
)

// ---- 页面跳转后焦点移到页面标题（首页移到始发站区域） ----
router.afterEach((to, from) => {
  if (to.path === from.path) return
  void nextTick(() => {
    window.setTimeout(() => {
      const target =
        document.querySelector<HTMLElement>("[data-page-focus]") ?? document.querySelector<HTMLElement>("[data-page-title]")
      target?.focus({ preventScroll: true })
    }, 0)
  })
})

// 关闭窗口前执行待撤销的删除
function onPageHide() {
  ui.flushPendingCommits()
}

onMounted(async () => {
  window.addEventListener("pagehide", onPageHide)
  try {
    await settingsStore.load()
    const theme = settingsStore.settings?.theme
    if (theme && theme !== ui.themeSetting) ui.setTheme(theme)
  } catch (e) {
    notifyError(e)
  }
  await Promise.allSettled([models.load(), prompts.load(), jobs.load()])
})

onBeforeUnmount(() => window.removeEventListener("pagehide", onPageHide))
</script>

<template>
  <TooltipProvider :delay-duration="400">
    <div class="ws-app">
      <nav class="ws-nav" aria-label="主导航">
        <RouterLink to="/" class="ws-nav__logo" aria-label="文枢首页">
          <Logo :size="28" />
        </RouterLink>
        <ul class="ws-nav__list">
          <li v-for="item in NAV" :key="item.key">
            <RouterLink
              :to="item.to"
              class="ws-nav__item"
              :class="{ 'is-active': activeNav === item.key }"
              :aria-current="activeNav === item.key ? 'page' : undefined"
            >
              <span class="ws-nav__icon">
                <component :is="item.icon" :size="22" :stroke-width="1.75" aria-hidden="true" />
                <span v-if="item.key === 'jobs' && hasRunning" class="ws-nav__dot" aria-hidden="true" />
              </span>
              <span class="ws-nav__label">{{ item.label }}</span>
              <span v-if="item.key === 'jobs' && hasRunning" class="sr-only">，有任务正在运行</span>
            </RouterLink>
          </li>
        </ul>
        <div class="ws-nav__bottom">
          <Tooltip :content="themeLabel" shortcut="ctrl+shift+l" side="right">
            <button type="button" class="ws-nav__theme" :aria-label="themeLabel" @click="toggleTheme">
              <component :is="themeIcon" :size="20" :stroke-width="1.75" aria-hidden="true" />
            </button>
          </Tooltip>
        </div>
      </nav>

      <div class="ws-main">
        <header class="ws-pagebar">
          <h1 v-if="pageTitle" class="ws-pagebar__title" data-page-title tabindex="-1">{{ pageTitle }}</h1>
          <span class="ws-pagebar__spacer" />
          <span v-if="ui.reconnecting" class="ws-pagebar__reconnect" role="status">正在重新连接</span>
          <button type="button" class="ws-pagebar__palette" aria-label="搜索或输入命令（Ctrl K）" @click="openPalette">
            <Search :size="16" :stroke-width="1.75" aria-hidden="true" />
            <span>搜索或输入命令</span>
            <span class="ws-pagebar__keys"><Kbd>Ctrl</Kbd><Kbd>K</Kbd></span>
          </button>
        </header>
        <main class="ws-content">
          <RouterView v-slot="{ Component: page }">
            <Transition name="ws-route">
              <component :is="page" />
            </Transition>
          </RouterView>
        </main>
      </div>
    </div>

    <CommandPalette />
    <ShortcutsDialog />
    <DropOverlay />
    <Toaster position="bottom-right" :visible-toasts="3" :duration="4000" :theme="ui.resolvedTheme" />
  </TooltipProvider>
</template>

<style scoped>
.ws-app {
  display: grid;
  grid-template-columns: var(--nav-width) minmax(0, 1fr);
  min-height: 100vh;
}

.ws-nav {
  position: sticky;
  top: 0;
  z-index: var(--z-nav);
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100vh;
  padding: var(--space-4) 0;
  border-right: 1px solid var(--border);
  background: var(--surface);
}

.ws-nav__logo {
  display: inline-flex;
  margin-bottom: var(--space-6);
  border-radius: var(--radius-control);
}

.ws-nav__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 100%;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ws-nav__item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  height: 56px;
  margin: 0 var(--space-2);
  border-radius: var(--radius-control);
  color: var(--ink-2);
  text-decoration: none;
  transition:
    color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}

.ws-nav__item:hover {
  background: var(--surface-2);
  color: var(--ink);
}

/* 当前入口：左边缘一条 4 px 宽、24 px 高的墨色竖线，像线路图上标注当前位置 */
.ws-nav__item.is-active {
  color: var(--ink);
}

.ws-nav__item.is-active::before {
  content: "";
  position: absolute;
  left: calc(-1 * var(--space-2));
  top: 16px;
  width: 4px;
  height: 24px;
  border-radius: 0 2px 2px 0;
  background: var(--ink);
}

.ws-nav__item.is-active .ws-nav__label {
  font-weight: 500;
}

.ws-nav__icon {
  position: relative;
  display: inline-flex;
}

.ws-nav__dot {
  position: absolute;
  top: -1px;
  right: -3px;
  width: 6px;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--status-running);
  box-shadow: 0 0 0 2px var(--surface);
}

.ws-nav__label {
  font-size: var(--text-xs);
  line-height: 1.3;
}

.ws-nav__bottom {
  margin-top: auto;
}

.ws-nav__theme {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--ink-2);
}

.ws-nav__theme:hover {
  background: var(--surface-2);
  color: var(--ink);
}

.ws-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ws-pagebar {
  position: sticky;
  top: 0;
  z-index: calc(var(--z-nav) - 1);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  height: var(--pagebar-height);
  padding: 0 var(--content-pad);
  background: var(--bg);
}

.ws-pagebar__title {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: 700;
  line-height: 1.4;
}

.ws-pagebar__spacer {
  flex: 1;
}

.ws-pagebar__reconnect {
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--status-warn) 14%, transparent);
  color: var(--status-warn);
  font-size: var(--text-xs);
  font-weight: 500;
}

.ws-pagebar__palette {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  width: 300px;
  height: 36px;
  padding: 0 var(--space-2) 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink-2);
  font-size: var(--text-sm);
  text-align: left;
}

.ws-pagebar__palette:hover {
  color: var(--ink);
}

.ws-pagebar__keys {
  display: inline-flex;
  gap: 2px;
  margin-left: auto;
}

.ws-content {
  flex: 1;
  min-width: 0;
  padding: 0 var(--content-pad) var(--space-12);
}

.ws-route-enter-active {
  transition: opacity 120ms var(--ease-out);
}

.ws-route-enter-from {
  opacity: 0;
}
</style>
