"""生成 packaging/icon.ico：exe 图标和托盘图标（07 第 2.4 节）。

Pillow 不能渲染 SVG，这里用基本图形按 icon.svg 的同一套几何直接画：先按 4 倍尺寸绘制，再缩小，
输出 16、24、32、48、64、128、256 px 七种尺寸。几何（48×48 坐标，与 packaging/icon.svg 一致）：
- 左侧墨色短线 M3 24H11，宽 3.5，圆头；
- 右上蓝线 M35 21.5 L39.5 17 H45（线路色 0，#0B6FD6），右下绿线 M35 26.5 L39.5 31 H45（线路色 1，#2DBE6C，
  06 第 3.3 节的亮色值），宽 3.5，圆头圆角；
- 枢纽胶囊 rect x=11 y=17 w=24 h=14 rx=7，填 #FFFFFF，描边 #1E2B38 宽 2.5，最后绘制（盖住彩线的起点）。
16 px 省略左侧短线和描边细节，只保留胶囊（实心墨色）和两段加粗的彩线，整体左移居中。

运行：backend\\.venv\\Scripts\\python.exe packaging\\make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT_FILE = Path(__file__).resolve().parent / "icon.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
SUPERSAMPLE = 4

INK = (0x1E, 0x2B, 0x38, 255)
WHITE = (0xFF, 0xFF, 0xFF, 255)
BLUE = (0x0B, 0x6F, 0xD6, 255)
GREEN = (0x2D, 0xBE, 0x6C, 255)

Point = tuple[float, float]
Color = tuple[int, int, int, int]


def draw_logo(size: int) -> Image.Image:
    big = size * SUPERSAMPLE
    scale = big / 48
    simple = size <= 16
    dx = -4.0 if simple else 0.0  # 16 px 去掉左侧短线后整体左移，保持居中

    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def pt(x: float, y: float) -> Point:
        return ((x + dx) * scale, y * scale)

    def polyline(points: list[Point], color: Color, width: float) -> None:
        w = width * scale
        draw.line([pt(x, y) for x, y in points], fill=color, width=max(1, round(w)), joint="curve")
        r = w / 2
        for x, y in (points[0], points[-1]):
            cx, cy = pt(x, y)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)

    blue = [(35.0, 21.5), (39.5, 17.0), (45.0, 17.0)]
    green = [(35.0, 26.5), (39.5, 31.0), (45.0, 31.0)]
    if simple:
        polyline(blue, BLUE, 5.0)
        polyline(green, GREEN, 5.0)
        draw.rounded_rectangle((*pt(10, 16), *pt(36, 32)), radius=8 * scale, fill=INK)
    else:
        polyline([(3.0, 24.0), (11.0, 24.0)], INK, 3.5)
        polyline(blue, BLUE, 3.5)
        polyline(green, GREEN, 3.5)
        half = 1.25  # 描边宽 2.5，居中在路径上；Pillow 的描边向内画，所以外框放大半个描边宽
        draw.rounded_rectangle(
            (*pt(11 - half, 17 - half), *pt(35 + half, 31 + half)),
            radius=(7 + half) * scale,
            fill=WHITE,
            outline=INK,
            width=max(1, round(2.5 * scale)),
        )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> int:
    frames = {size: draw_logo(size) for size in SIZES}
    largest = frames[max(SIZES)]
    others = [frames[size] for size in SIZES if size != max(SIZES)]
    # append_images 里有对应尺寸的图时，Pillow 直接使用它（16 px 用简化画法），不再缩放
    largest.save(OUT_FILE, format="ICO", sizes=[(s, s) for s in SIZES], append_images=others)
    print(f"已生成 {OUT_FILE}（{', '.join(str(s) for s in SIZES)} px）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
