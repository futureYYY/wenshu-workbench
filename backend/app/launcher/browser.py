"""查找 Edge、Chrome，以应用模式打开独立窗口（07 第 5.2 节）。"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

_APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
# 启动的浏览器进程不等待；保留引用，避免对象回收时报“子进程仍在运行”的警告
_children: list[subprocess.Popen[bytes]] = []


def _registry_lookup(exe: str) -> Path | None:
    if sys.platform != "win32":
        return None
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, f"{_APP_PATHS}\\{exe}") as key:
                value, _kind = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            path = Path(os.path.expandvars(value.strip().strip('"')))
            if path.is_file():
                return path
    return None


def _common_paths(exe: str) -> list[Path]:
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    program_files = os.environ.get("ProgramFiles", "")
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if exe == "msedge.exe":
        relative = Path("Microsoft") / "Edge" / "Application" / exe
        roots = [program_files_x86, program_files]
    else:
        relative = Path("Google") / "Chrome" / "Application" / exe
        roots = [program_files_x86, program_files, local_app_data]
    return [Path(root) / relative for root in roots if root]


def find_browser() -> Path | None:
    """依次查找：注册表 App Paths 和常见安装路径中的 msedge.exe，然后是 chrome.exe。"""
    for exe in ("msedge.exe", "chrome.exe"):
        found = _registry_lookup(exe)
        if found is not None:
            return found
        for candidate in _common_paths(exe):
            if candidate.is_file():
                return candidate
    return None


def open_default_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        logger.exception("用默认浏览器打开 %s 失败", url)


def open_app_window(url: str, user_data_dir: Path) -> bool:
    """用 --app 打开没有标签栏和地址栏的独立窗口。找不到浏览器时退回默认浏览器，返回 False。"""
    exe = find_browser()
    if exe is None:
        logger.warning("没有找到 Edge 或 Chrome，改用默认浏览器打开 %s", url)
        open_default_browser(url)
        return False
    user_data_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(exe),
        f"--app={url}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1600,1000",
    ]
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    try:
        child = subprocess.Popen(
            args,
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.warning("启动 %s 失败（%s），改用默认浏览器", exe, exc)
        open_default_browser(url)
        return False
    _children.append(child)
    logger.info("已用 %s 打开独立窗口", exe.name)
    return True


def open_ui(url: str, *, mode: str, user_data_dir: Path, force_browser: bool = False) -> None:
    """按设置的打开方式打开界面：app 为独立窗口（默认），browser 为默认浏览器。"""
    if force_browser or mode == "browser":
        open_default_browser(url)
    else:
        open_app_window(url, user_data_dir)
