/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 接口地址；为空表示与页面同源（02 第 1.1 节） */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
