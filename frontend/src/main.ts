// 字体随前端打包，断网也能显示（07 第 2.3 节）
import "@fontsource-variable/noto-sans-sc"
import "@fontsource-variable/overpass"
import "@fontsource/overpass-mono/400.css"
import "vue-sonner/style.css"
import "./design/base.css"

import { createPinia } from "pinia"
import { createApp } from "vue"
import App from "./App.vue"
import { router } from "./router"

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount("#app")
