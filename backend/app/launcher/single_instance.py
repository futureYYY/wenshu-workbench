"""单实例：同一个数据目录只允许运行一个实例（07 第 5.1 节第 2 步）。

Windows 用命名互斥量（CreateMutexW）；其他平台退化为数据目录里的文件锁，方便在 Linux 上测试。
打包版和源码版默认数据目录不同，所以可以同时运行。
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from typing import IO, Any

from app import APP_ID

logger = logging.getLogger(__name__)

ERROR_ALREADY_EXISTS = 183


def mutex_name(data_dir: Path) -> str:
    """名称为 "Local\\WenShu." + sha1(数据目录绝对路径转小写)[:12]。"""
    digest = hashlib.sha1(str(Path(data_dir).resolve()).lower().encode("utf-8")).hexdigest()[:12]
    return f"Local\\{APP_ID}.{digest}"


class InstanceLock:
    """持有期间，其他实例拿不到同一个数据目录的锁。release() 可以重复调用。"""

    def release(self) -> None:
        return None


class _WindowsMutex(InstanceLock):
    def __init__(self, handle: int, kernel32: Any) -> None:
        self._handle: int | None = handle
        self._kernel32 = kernel32

    def release(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class _FileLock(InstanceLock):
    def __init__(self, handle: IO[str]) -> None:
        self._handle: IO[str] | None = handle

    def release(self) -> None:
        if self._handle is not None:
            self._handle.close()  # 关闭文件即释放 flock
            self._handle = None


def _acquire_windows(name: str) -> InstanceLock | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateMutexW(None, False, name)
    error = ctypes.get_last_error()
    if not handle:
        # 拿不到互斥量时不阻止启动，只是失去单实例保护
        logger.warning("CreateMutexW 失败（错误码 %s），跳过单实例检查", error)
        return InstanceLock()
    if error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return _WindowsMutex(handle, kernel32)


def _acquire_posix(data_dir: Path) -> InstanceLock | None:
    import fcntl

    data_dir.mkdir(parents=True, exist_ok=True)
    handle = (data_dir / ".instance.lock").open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return _FileLock(handle)


def acquire(data_dir: Path) -> InstanceLock | None:
    """拿到锁返回 InstanceLock；已有实例在运行（同一数据目录）返回 None。"""
    if sys.platform == "win32":
        return _acquire_windows(mutex_name(data_dir))
    try:
        return _acquire_posix(Path(data_dir))
    except (ImportError, OSError) as exc:
        logger.warning("文件锁不可用（%s），跳过单实例检查", exc)
        return InstanceLock()
