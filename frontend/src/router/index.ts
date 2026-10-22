/** 前端路由（04 第 12 节），全部懒加载。 */
import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"

declare module "vue-router" {
  interface RouteMeta {
    /** 页面栏标题；首页不显示 */
    title?: string
    /** 导航栏里高亮哪一项 */
    nav?: "home" | "jobs" | "prompts" | "models" | "settings" | "about"
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "home",
    component: () => import("@/features/home/HomePage.vue"),
    meta: { nav: "home" },
  },
  {
    path: "/new",
    name: "new-job",
    component: () => import("@/features/new-job/NewJobPage.vue"),
    meta: { title: "新建任务", nav: "home" },
  },
  {
    path: "/jobs",
    name: "jobs",
    component: () => import("@/features/jobs/JobsPage.vue"),
    meta: { title: "任务中心", nav: "jobs" },
  },
  {
    path: "/jobs/:id(\\d+)",
    name: "job",
    component: () => import("@/features/job-detail/JobDetailPage.vue"),
    meta: { title: "任务详情", nav: "jobs" },
  },
  {
    path: "/jobs/:id(\\d+)/read/:itemId(\\d+)",
    name: "reading",
    component: () => import("@/features/reading/ReadingPage.vue"),
    meta: { title: "对照阅读", nav: "jobs" },
  },
  {
    // 不带 id 时进入意图识别的默认模板；同一个路由记录，切换模板时页面不重新挂载
    path: "/prompts/:id(\\d+)?",
    name: "prompts",
    component: () => import("@/features/prompts/PromptsPage.vue"),
    meta: { title: "提示词工坊", nav: "prompts" },
  },
  {
    path: "/models",
    name: "models",
    component: () => import("@/features/models/ModelsPage.vue"),
    meta: { title: "模型接入", nav: "models" },
  },
  {
    path: "/settings",
    name: "settings",
    component: () => import("@/features/settings/SettingsPage.vue"),
    meta: { title: "设置", nav: "settings" },
  },
  {
    path: "/about",
    name: "about",
    component: () => import("@/features/about/AboutPage.vue"),
    meta: { title: "关于", nav: "about" },
  },
]

// 组件预览页只在开发模式注册
if (import.meta.env.DEV) {
  routes.push({
    path: "/_dev/components",
    name: "dev-components",
    component: () => import("@/features/dev-components/DevComponentsPage.vue"),
    meta: { title: "组件预览" },
  })
}

routes.push({ path: "/:pathMatch(.*)*", redirect: "/" })

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
