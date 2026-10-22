/**
 * 端到端测试的全局准备（08 第 10.4 节）：
 * - 确认 .e2edata 存在（清空在 playwright.config.ts 加载时已经做过，那时后端还没启动）；
 * - testdata/ 缺文件，或生成脚本改过（testdata/.make_testdata.sha256 里记录的脚本哈希对不上）时，
 *   用后端虚拟环境的 Python 运行 scripts/make_testdata.py（缺的补上；脚本改过时全部重新生成）。
 */
import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import { existsSync, mkdirSync, readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, "..", "..")
const python =
  process.platform === "win32"
    ? path.join(root, "backend", ".venv", "Scripts", "python.exe")
    : path.join(root, "backend", ".venv", "bin", "python")

/** 08 第 10.2 节列出的测试数据 */
const TESTDATA_FILES = [
  "utf8_big.csv",
  "export_edge.csv",
  "intent_200.xlsx",
  "gbk_1000.csv",
  "semicolon.csv",
  "utf16.txt",
  "bom.txt",
  "legacy.xls",
  "big_120k.csv",
  "long_texts.txt",
  "broken.xlsx",
]

export default function globalSetup(): void {
  mkdirSync(path.join(root, ".e2edata"), { recursive: true })

  const testdata = path.join(root, "testdata")
  const script = path.join(root, "scripts", "make_testdata.py")
  const missing = TESTDATA_FILES.filter((name) => !existsSync(path.join(testdata, name)))
  // 与 make_testdata.py 的 script_digest() 相同：脚本文件内容的 SHA-256
  const digest = createHash("sha256").update(readFileSync(script)).digest("hex")
  const stamp = path.join(testdata, ".make_testdata.sha256")
  const stale = !existsSync(stamp) || readFileSync(stamp, "utf8").trim() !== digest
  if (missing.length === 0 && !stale) return
  const reason = missing.length > 0 ? `缺少 ${missing.join("、")}` : "生成脚本有改动"
  if (!existsSync(python)) {
    throw new Error(`测试数据需要重新生成（${reason}），但找不到 ${python}。请先按 docs/07-packaging.md 第 2 节建好后端虚拟环境。`)
  }
  console.log(`生成测试数据（${reason}）`)
  execFileSync(python, [script], { cwd: root, stdio: "inherit" })
}
