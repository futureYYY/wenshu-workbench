"""托盘图标（07 第 5.3 节）。

只依赖 pystray 和 Pillow。pystray 在 Windows 上用 ctypes 实现；若以后遇到兼容问题，
改用 pywin32 自行实现时保持 Tray 的接口（run、stop、set_title、notify）不变即可。
没有图形环境或 pystray 不可用时退化为“无托盘”：run() 阻塞到 stop() 被调用。
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import APP_ID

logger = logging.getLogger(__name__)

# Logo 几何（48×48 坐标）和颜色（墨色、线路色 0 蓝、线路色 1 绿的亮色值，06 第 2、3.3 节），
# 与 packaging/icon.svg、packaging/make_icon.py 一致
INK = (0x1E, 0x2B, 0x38, 255)
WHITE = (0xFF, 0xFF, 0xFF, 255)
BLUE = (0x0B, 0x6F, 0xD6, 255)
GREEN = (0x2D, 0xBE, 0x6C, 255)
TRAY_ICON_SIZE = 64


def draw_logo(size: int = TRAY_ICON_SIZE) -> Any:
    """没有 icon.ico 时用 Pillow 现画一个托盘图标（4 倍尺寸绘制后缩小）。"""
    from PIL import Image, ImageDraw

    big = size * 4
    scale = big / 48
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def pt(x: float, y: float) -> tuple[float, float]:
        return (x * scale, y * scale)

    def polyline(points: list[tuple[float, float]], color: tuple[int, int, int, int], width: float) -> None:
        w = width * scale
        draw.line([pt(x, y) for x, y in points], fill=color, width=max(1, round(w)), joint="curve")
        r = w / 2
        for x, y in (points[0], points[-1]):
            cx, cy = pt(x, y)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)

    # 绘制顺序与 icon.svg 相同：左侧墨线、两段彩线，最后是胶囊（盖住彩线的起点）
    polyline([(3, 24), (11, 24)], INK, 3.5)
    polyline([(35, 21.5), (39.5, 17), (45, 17)], BLUE, 3.5)
    polyline([(35, 26.5), (39.5, 31), (45, 31)], GREEN, 3.5)
    half = 1.25  # 描边宽 2.5，居中在路径上
    draw.rounded_rectangle(
        (*pt(11 - half, 17 - half), *pt(35 + half, 31 + half)),
        radius=(7 + half) * scale,
        fill=WHITE,
        outline=INK,
        width=max(1, round(2.5 * scale)),
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def load_icon_image(paths: list[Path]) -> Any:
    """依次尝试 icon.ico（取最大的一张缩到 64 px），都没有时现画。"""
    from PIL import Image

    for path in paths:
        if not path.is_file():
            continue
        try:
            with Image.open(path) as opened:
                opened.load()
                image = opened.convert("RGBA")
        except OSError as exc:
            logger.warning("读取托盘图标 %s 失败：%s", path, exc)
            continue
        if image.size != (TRAY_ICON_SIZE, TRAY_ICON_SIZE):
            image = image.resize((TRAY_ICON_SIZE, TRAY_ICON_SIZE), Image.Resampling.LANCZOS)
        return image
    logger.info("没有找到 icon.ico，托盘图标改为现画")
    return draw_logo(TRAY_ICON_SIZE)


class Tray:
    """托盘图标与菜单：打开文枢（默认项，左键单击也执行它）、打开数据目录、分隔线、退出。"""

    def __init__(
        self,
        *,
        title: str,
        icon_paths: list[Path],
        on_open: Callable[[], None],
        on_open_data_dir: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self._title = title
        self._icon_paths = icon_paths
        self._on_open = on_open
        self._on_open_data_dir = on_open_data_dir
        self._on_exit = on_exit
        self._icon: Any = None
        self._stopped = threading.Event()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def run(self, worker: Callable[[], None] | None = None) -> None:
        """在主线程运行托盘消息循环，直到 stop()。worker 在后台线程里执行。"""
        if self._stopped.is_set():
            return
        try:
            import pystray

            image = load_icon_image(self._icon_paths)
            menu = pystray.Menu(
                pystray.MenuItem("打开文枢", lambda icon, item: self._call(self._on_open), default=True),
                pystray.MenuItem("打开数据目录", lambda icon, item: self._call(self._on_open_data_dir)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda icon, item: self._call(self._on_exit)),
            )
            icon = pystray.Icon(APP_ID, image, self._title, menu)
        except Exception as exc:  # 没有图形环境、缺少依赖等
            logger.warning("托盘不可用（%s），程序在后台运行，直到收到退出请求", exc)
            self._run_headless(worker)
            return

        self._icon = icon

        def setup(ic: Any) -> None:
            ic.visible = True
            if worker is not None:
                threading.Thread(target=worker, name="wenshu-tray-worker", daemon=True).start()
            if self._stopped.is_set():
                ic.stop()

        try:
            icon.run(setup=setup)
        except Exception:
            logger.exception("托盘运行出错，改为无托盘模式")
            self._icon = None
            self._run_headless(None)
        finally:
            self._icon = None

    def stop(self) -> None:
        """可以在任何线程调用。"""
        self._stopped.set()
        icon = self._icon
        if icon is not None:
            with contextlib.suppress(Exception):
                icon.stop()

    def set_title(self, title: str) -> None:
        """更新悬停提示（Windows 限 127 个字符）。"""
        self._title = title[:127]
        icon = self._icon
        if icon is not None:
            with contextlib.suppress(Exception):
                icon.title = self._title

    def notify(self, message: str, title: str) -> None:
        """托盘气泡通知。不支持时只记日志。"""
        icon = self._icon
        if icon is None or not getattr(icon, "HAS_NOTIFICATION", True):
            logger.info("托盘通知：%s", message)
            return
        try:
            icon.notify(message, title)
        except Exception as exc:
            logger.warning("托盘通知失败：%s", exc)

    def _call(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception:
            logger.exception("托盘菜单操作失败")

    def _run_headless(self, worker: Callable[[], None] | None) -> None:
        if worker is not None:
            threading.Thread(target=worker, name="wenshu-tray-worker", daemon=True).start()
        self._stopped.wait()
