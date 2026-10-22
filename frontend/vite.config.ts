import { fileURLToPath, URL } from "node:url"
import tailwindcss from "@tailwindcss/vite"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"

// 开发服务器把接口转发到后端（07 第 3 节）。WENSHU_API_TARGET 只给开发服务器用，默认是 dev.bat 启动的后端；
// 端到端测试把它设为自己启动的后端 http://127.0.0.1:18766（08 第 10.4 节）。正式构建不受影响。
// changeOrigin 让转发后的 Host 变成后端的地址，才能通过后端的 Host 检查（02 第 10 节）。
const apiTarget = process.env.WENSHU_API_TARGET ?? "http://127.0.0.1:18765"
const proxied = { target: apiTarget, changeOrigin: true }

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": proxied,
      "/mock": proxied,
      "/docs": proxied,
      "/docs-assets": proxied,
      "/openapi.json": proxied,
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    // CodeMirror 和中文字体子集体积较大，只是提示阈值，保持默认分包
    chunkSizeWarningLimit: 1500,
  },
})
