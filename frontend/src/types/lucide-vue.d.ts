/**
 * @lucide/vue 的类型声明（只声明本项目用到的图标）。
 *
 * 官方包的 package.json 用 typings 指向 dist/lucide-vue.d.ts，但本机联调时装出来的包里没有这个文件，
 * vue-tsc 报 TS7016（模块隐式为 any）。这里是环境模块声明，TypeScript 解析 "@lucide/vue" 时优先用它，
 * 包里有没有自带类型，类型检查的结果都一样。
 *
 * 类型照抄官方 1.61.0 的 LucideProps、LucideIcon。新用到一个图标时在下面按字母顺序补一行，
 * 名字要和官方导出的一致（拼错了 vite build 会报“没有这个导出”）。
 */
declare module "@lucide/vue" {
  import type { FunctionalComponent, SVGAttributes } from "vue"

  export interface LucideProps extends Partial<SVGAttributes> {
    size?: number
    strokeWidth?: number | string
    /** @deprecated 官方建议改用 nonScalingStroke */
    absoluteStrokeWidth?: boolean
    /** @deprecated 官方建议改用 non-scaling-stroke */
    "absolute-stroke-width"?: boolean
    nonScalingStroke?: boolean
    "non-scaling-stroke"?: boolean
  }

  export type LucideIcon = FunctionalComponent<LucideProps>

  export const ArrowDown: LucideIcon
  export const ArrowLeft: LucideIcon
  export const ArrowUp: LucideIcon
  export const Ban: LucideIcon
  export const Check: LucideIcon
  export const ChevronDown: LucideIcon
  export const ChevronRight: LucideIcon
  export const CircleCheck: LucideIcon
  export const CircleMinus: LucideIcon
  export const CircleX: LucideIcon
  export const Clock: LucideIcon
  export const Copy: LucideIcon
  export const Cpu: LucideIcon
  export const Download: LucideIcon
  export const Ellipsis: LucideIcon
  export const Eye: LucideIcon
  export const EyeOff: LucideIcon
  export const FolderOpen: LucideIcon
  export const Heart: LucideIcon
  export const House: LucideIcon
  export const Info: LucideIcon
  export const List: LucideIcon
  export const ListChecks: LucideIcon
  export const MessageCircle: LucideIcon
  export const MessageSquareText: LucideIcon
  export const Moon: LucideIcon
  export const PanelRightClose: LucideIcon
  export const PanelRightOpen: LucideIcon
  export const Pause: LucideIcon
  export const Pencil: LucideIcon
  export const Play: LucideIcon
  export const Plus: LucideIcon
  export const RotateCcw: LucideIcon
  export const Search: LucideIcon
  export const Settings: LucideIcon
  export const Split: LucideIcon
  export const Square: LucideIcon
  export const Sun: LucideIcon
  export const SunMoon: LucideIcon
  export const Trash2: LucideIcon
  export const TriangleAlert: LucideIcon
  export const X: LucideIcon
}
