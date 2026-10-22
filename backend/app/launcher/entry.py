"""启动流程（07 第 5.1 节），打包版和源码版共用，两个入口都只调用这里的 main()：

- 打包版：PyInstaller 的入口脚本 packaging/wenshu_main.py（07 第 6 节）；
- 源码版：启动文枢.bat 执行 pythonw.exe -m app.launcher（app/launcher/__main__.py，07 第 5.5 节）。

本包只用绝对导入（from app.launcher import …）：打包入口不在包内，相对导入要到打包后才报错。
命令行参数：--selftest（自检后退出）、--browser（这一次用默认浏览器）、--no-open（不打开界面）。
窗口程序没有控制台（sys.stdout、sys.stderr 为 None），所有输出只写日志文件。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import multiprocessing
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app import APP_NAME, __version__
from app.config import DEFAULT_PORT, AppConfig, is_frozen, load_config, setup_logging
from app.launcher import browser, localhttp, ports, single_instance
from app.launcher.tray import Tray

logger = logging.getLogger("app.launcher")

HEALTH_TIMEOUT_S = 15.0
# 退出第 1 步：在后端事件循环里暂停任务、等进行中的请求、提交写入队列，最多等这么久
JOB_SHUTDOWN_TIMEOUT_S = 10.0
# 退出第 4 步：等后端线程结束的上限
SHUTDOWN_TIMEOUT_S = 15.0
# Uvicorn 停止时等现有连接结束的上限，最后一道保险（事件流已在第 2 步结束，正常不会等满）
GRACEFUL_SHUTDOWN_S = 5
FIRST_CLOSE_HINT = "文枢仍在后台运行，可以从这里重新打开或退出"


# ---------------------------------------------------------------- 小工具


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def message_box(text: str, *, error: bool = True) -> None:
    """弹出系统消息框（Windows）；其他平台只记日志。"""
    if error:
        logger.error(text)
    else:
        logger.info(text)
    if sys.platform != "win32":
        return
    import ctypes

    mb_iconerror, mb_iconinformation, mb_setforeground = 0x10, 0x40, 0x10000
    flags = (mb_iconerror if error else mb_iconinformation) | mb_setforeground
    with contextlib.suppress(Exception):
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags)


def read_setting(db_path: Path, key: str) -> Any:
    """用标准库 sqlite3 读一个设置项；数据库或设置不存在时返回 None。"""
    if not db_path.is_file():
        return None
    try:
        with contextlib.closing(sqlite3.connect(str(db_path), timeout=5)) as conn:
            row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error as exc:
        logger.warning("读取设置 %s 失败：%s", key, exc)
        return None
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def write_setting(db_path: Path, key: str, value: Any) -> bool:
    try:
        with contextlib.closing(sqlite3.connect(str(db_path), timeout=5)) as conn, conn:
            conn.execute(
                "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                (key, json.dumps(value), _utc_now()),
            )
    except sqlite3.Error as exc:
        logger.warning("写入设置 %s 失败：%s", key, exc)
        return False
    return True


def _read_preferred_port(db_path: Path) -> int:
    value = read_setting(db_path, "preferred_port")
    if isinstance(value, int) and not isinstance(value, bool) and 1024 <= value <= 65535:
        return value
    return DEFAULT_PORT


def _read_runtime_port(cfg: AppConfig) -> int | None:
    try:
        data = json.loads(cfg.runtime_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    port = data.get("port") if isinstance(data, dict) else None
    return port if isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536 else None


def _write_runtime(cfg: AppConfig, port: int) -> None:
    payload = {"port": port, "pid": os.getpid(), "version": __version__, "started_at": _utc_now()}
    tmp = cfg.runtime_file.with_name(cfg.runtime_file.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(cfg.runtime_file)
    except OSError as exc:
        logger.warning("写入 %s 失败：%s", cfg.runtime_file, exc)


def _remove_runtime(cfg: AppConfig) -> None:
    try:
        data = json.loads(cfg.runtime_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, dict) and data.get("pid") == os.getpid():
        with contextlib.suppress(OSError):
            cfg.runtime_file.unlink()


def _fetch_open_mode(port: int) -> str:
    try:
        data = localhttp.get_json(port, "/api/settings", timeout=3)
    except localhttp.ERRORS:
        return "app"
    mode = data.get("open_mode") if isinstance(data, dict) else None
    return mode if mode in ("app", "browser") else "app"


def _open_ui(cfg: AppConfig, port: int, *, force_browser: bool) -> None:
    url = f"http://{ports.HOST}:{port}/"
    try:
        browser.open_ui(url, mode=_fetch_open_mode(port), user_data_dir=cfg.browser_dir, force_browser=force_browser)
    except Exception:
        logger.exception("打开界面失败")


def _open_folder(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        logger.exception("打开目录 %s 失败", path)


def _icon_paths(cfg: AppConfig) -> list[Path]:
    paths = [cfg.bundle_dir / "icon.ico"]  # 打包版：spec 把 icon.ico 放在 _internal 根目录
    if not is_frozen():
        paths.append(cfg.app_dir.parent / "packaging" / "icon.ico")  # 源码版：项目根目录的 packaging
    return paths


def _startup_failure_message(cfg: AppConfig) -> str:
    log_path = cfg.logs_dir / "app.log"
    failed_migration = False
    with contextlib.suppress(Exception):
        from app.db import migrate

        failed_migration = bool(getattr(migrate, "last_error", None))
    if failed_migration:
        return f"文枢启动失败：数据库升级失败，详情见 {log_path}"
    return f"文枢启动失败，详情见 {log_path}"


def _install_excepthooks() -> None:
    def handle(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        logger.critical("未捕获的异常", exc_info=(exc_type, exc, tb))

    def handle_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread is not None else "?"
        exc_value = args.exc_value if args.exc_value is not None else args.exc_type()
        logger.critical("线程 %s 中未捕获的异常", name, exc_info=(args.exc_type, exc_value, args.exc_traceback))

    sys.excepthook = handle
    threading.excepthook = handle_thread


def _safe_int(obj: Any, *names: str) -> int:
    try:
        for name in names:
            obj = getattr(obj, name)
        return int(obj)
    except (AttributeError, TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- 后端线程


def start_backend(cfg: AppConfig, sock: Any, *, exit_callback: Any = None) -> tuple[Any, Any, threading.Thread]:
    """在后台线程运行 Uvicorn（使用已经绑定的 socket），返回 (app, server, thread)。自检也用它。

    应用的 lifespan 启动完成后，会把后端线程的事件循环和 JobManager 放在 app.state.loop、
    app.state.job_manager 上，退出时 stop_backend 用它们在后端线程里暂停任务（07 第 5.1 节第 4、9 步）。"""
    import uvicorn

    from app.main import create_app

    port = ports.socket_port(sock)
    os.environ["WENSHU_PORT"] = str(port)
    app = create_app(data_dir=cfg.data_dir, port=port, exit_callback=exit_callback)
    config = uvicorn.Config(
        app=app,
        host=ports.HOST,
        port=port,
        log_config=None,
        access_log=False,
        lifespan="on",
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, name="wenshu-backend", daemon=True)
    thread.start()
    return app, server, thread


def wait_until_ready(port: int, thread: threading.Thread, timeout: float = HEALTH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not thread.is_alive():
            return False  # 启动失败（例如迁移出错），后端线程已经结束
        if localhttp.health_ok(port, timeout=1.0):
            return True
        time.sleep(0.2)
    return False


def _shutdown_jobs(app: Any) -> None:
    """退出第 1 步：在后端的事件循环里执行 JobManager.shutdown()（02 第 5.7 节第 1–3 步：暂停任务、
    等进行中的请求、写入协程全部提交），等它完成。后端还没就绪（没有事件循环或 JobManager）时跳过。"""
    state = getattr(app, "state", None)
    loop = getattr(state, "loop", None)
    manager = getattr(state, "job_manager", None)
    if loop is None or manager is None:
        logger.info("后端还没有就绪，跳过暂停任务")
        return
    if loop.is_closed() or not loop.is_running():
        logger.info("后端的事件循环已经停止，跳过暂停任务")
        return
    try:
        future = asyncio.run_coroutine_threadsafe(manager.shutdown(), loop)
    except RuntimeError as exc:  # 事件循环恰好在这时关闭
        logger.warning("无法在后端事件循环里暂停任务：%s", exc)
        return
    try:
        future.result(timeout=JOB_SHUTDOWN_TIMEOUT_S)
    except TimeoutError:
        future.cancel()
        logger.warning("暂停任务、保存结果在 %s 秒内没有完成，继续退出", int(JOB_SHUTDOWN_TIMEOUT_S))
    except Exception:
        logger.exception("退出时暂停任务失败，继续退出")


def _end_event_streams() -> None:
    """退出第 2 步：设置 sse-starlette 的退出标志，所有事件流随即结束（02 第 5.7 节第 4 步）。

    后端跑在非主线程里，Uvicorn 不安装信号处理器，sse-starlette 收不到退出通知；不先结束事件流，
    界面开着时 Uvicorn 会一直等这些长连接关闭。"""
    try:
        from sse_starlette.sse import AppStatus
    except ImportError as exc:
        logger.warning("无法结束事件流（%s），依靠 Uvicorn 的 timeout_graceful_shutdown 兜底", exc)
        return
    AppStatus.should_exit = True


def stop_backend(app: Any, server: Any, thread: threading.Thread, timeout: float = SHUTDOWN_TIMEOUT_S) -> None:
    """按 07 第 5.1 节第 9 步的第 1–4 步退出后端，在主线程里调用（托盘模式和自检共用）：
    暂停任务并提交结果 → 结束事件流 → 通知 Uvicorn 停止 → 等后端线程结束。顺序不能换：
    第 2 步必须在第 3 步之前。应用的 lifespan 关闭时还会再执行一遍暂停（没有副作用），然后关闭连接。"""
    _shutdown_jobs(app)
    _end_event_streams()
    server.should_exit = True
    thread.join(timeout)
    if thread.is_alive():
        logger.warning("后端在 %s 秒内没有结束，直接退出", int(timeout))


# ---------------------------------------------------------------- 主流程


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="WenShu", description=f"{APP_NAME}启动器")
    parser.add_argument("--selftest", action="store_true", help="不打开界面，自检后退出，用退出码表示结果")
    parser.add_argument("--browser", action="store_true", help="这一次用默认浏览器打开界面")
    parser.add_argument("--no-open", action="store_true", help="不打开界面，只在托盘运行")
    args, _unknown = parser.parse_known_args(argv)
    return args


def _activate_existing(cfg: AppConfig, args: argparse.Namespace) -> int:
    """已有实例在运行：读取它的端口，确认健康后直接打开界面。"""
    port = _read_runtime_port(cfg)
    if port is not None:
        for attempt in range(5):
            if localhttp.health_ok(port, timeout=2.0):
                logger.info("文枢已在运行（端口 %s），直接打开界面", port)
                if not args.no_open:
                    _open_ui(cfg, port, force_browser=args.browser)
                return 0
            if attempt < 4:
                time.sleep(1.0)
    message_box("文枢已在运行但没有响应。请在任务栏右下角的文枢图标上右键选择退出，然后重新打开。")
    return 1


def _monitor(app: Any, tray: Tray, cfg: AppConfig, stop: threading.Event) -> None:
    """托盘后台线程：每 5 秒更新悬停提示；界面窗口第一次被关掉时弹一次气泡（07 第 5.3 节）。"""
    hint_pending = read_setting(cfg.db_path, "first_close_hint_shown") is not True
    had_client = False
    zero_since: float | None = None
    last_title = ""
    tick = 0
    while not stop.wait(1.0):
        ctx = getattr(app.state, "ctx", None)
        if ctx is None:
            continue  # 后端还没就绪
        if tick % 5 == 0:
            running = _safe_int(ctx, "manager", "running_count")
            title = APP_NAME if running <= 0 else f"{APP_NAME}：{running} 个任务运行中"
            if title != last_title:
                tray.set_title(title)
                last_title = title
        tick += 1
        if not hint_pending:
            continue
        clients = _safe_int(ctx, "bus", "global_subscriber_count")
        if clients >= 1:
            had_client, zero_since = True, None
            continue
        if not had_client:
            continue
        now = time.monotonic()
        if zero_since is None:
            zero_since = now
            continue
        if now - zero_since >= 3.0:
            hint_pending = False
            if read_setting(cfg.db_path, "first_close_hint_shown") is True:
                continue
            tray.notify(FIRST_CLOSE_HINT, APP_NAME)
            write_setting(cfg.db_path, "first_close_hint_shown", True)


def _run(cfg: AppConfig, args: argparse.Namespace) -> int:
    sock = ports.bind_socket(_read_preferred_port(cfg.db_path))
    port = ports.socket_port(sock)
    exit_requested = threading.Event()

    tray = Tray(
        title=APP_NAME,
        icon_paths=_icon_paths(cfg),
        on_open=lambda: _open_ui(cfg, port, force_browser=args.browser),
        on_open_data_dir=lambda: _open_folder(cfg.data_dir),
        on_exit=lambda: request_exit(),
    )

    def request_exit() -> None:
        # 托盘“退出”和 /api/system/shutdown 的退出回调（在后端线程里调用）都走这里：只结束托盘循环，
        # 退出流程由主线程在 tray.run() 返回后按顺序执行（07 第 5.1 节第 9 步）
        if not exit_requested.is_set():
            logger.info("收到退出请求")
        exit_requested.set()
        tray.stop()

    app, server, thread = start_backend(cfg, sock, exit_callback=request_exit)
    logger.info("后端线程已启动，端口 %s", port)

    if not wait_until_ready(port, thread):
        stop_backend(app, server, thread)
        message_box(_startup_failure_message(cfg))
        return 1

    _write_runtime(cfg, port)
    try:
        if exit_requested.is_set():
            return 0
        if not args.no_open:
            _open_ui(cfg, port, force_browser=args.browser)
        tray.run(worker=lambda: _monitor(app, tray, cfg, exit_requested))
    finally:
        exit_requested.set()
        logger.info("正在退出：暂停任务、保存结果、结束事件流")
        stop_backend(app, server, thread)
        _remove_runtime(cfg)  # 第 5 步：删除 runtime.json；互斥量在 main() 里释放
        logger.info("已退出")
    return 0


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    args = _parse_args(argv)
    if args.selftest:
        from app.launcher.selftest import run_selftest

        return run_selftest()

    cfg = load_config()
    try:
        cfg.ensure_dirs()
        setup_logging(cfg)
    except OSError as exc:
        message_box(f"文枢无法写入数据目录 {cfg.data_dir}：{exc}")
        return 1
    _install_excepthooks()
    logger.info("%s %s 启动：运行方式 %s，数据目录 %s", APP_NAME, __version__, cfg.run_mode, cfg.data_dir)

    lock = single_instance.acquire(cfg.data_dir)
    if lock is None:
        return _activate_existing(cfg, args)
    try:
        return _run(cfg, args)
    except Exception:
        logger.exception("启动器异常")
        message_box(_startup_failure_message(cfg))
        return 1
    finally:
        lock.release()
