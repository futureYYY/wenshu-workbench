import js from "@eslint/js"
import prettier from "eslint-config-prettier"
import { defineConfig } from "eslint/config"
import pluginVue from "eslint-plugin-vue"
import tseslint from "typescript-eslint"

// eslint-plugin-vue 的 flat 配置在不同大版本里叫 "flat/recommended" 或 "recommended"
const vueRecommended = pluginVue.configs["flat/recommended"] ?? pluginVue.configs.recommended

export default defineConfig([
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "test-results/**",
      "playwright-report/**",
      "src/api/schema.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...(Array.isArray(vueRecommended) ? vueRecommended : [vueRecommended]),
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        ecmaVersion: "latest",
        sourceType: "module",
      },
    },
  },
  prettier,
  {
    rules: {
      // 类型检查由 vue-tsc 负责，浏览器全局变量不需要 ESLint 再判断
      "no-undef": "off",
      // Button、Input 这类基础组件按惯例用单个单词命名
      "vue/multi-word-component-names": "off",
      "vue/no-reserved-component-names": "off",
      // 摘要里的 Markdown 先经 DOMPurify 清洗后才用 v-html 输出
      "vue/no-v-html": "off",
      "vue/require-default-prop": "off",
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" },
      ],
    },
  },
])
