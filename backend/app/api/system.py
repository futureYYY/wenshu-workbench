"""系统接口（04 第 3.1 节）。"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app import __version__
from app.api.errors import ERROR_RESPONSES, bad_request
from app.context import AppContext, get_ctx
from app.schemas.system import Health, OpenFolderRequest, ShutdownResult, SystemInfo
from app.services import settings_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["系统"], responses=ERROR_RESPONSES)


@router.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok", version=__version__)


@router.get("/system/info", response_model=SystemInfo)
async def get_system_info(ctx: AppContext = Depends(get_ctx)) -> SystemInfo:
    settings = await settings_service.get_settings(ctx.db)
    return SystemInfo(
        version=__version__,
        data_dir=str(ctx.cfg.data_dir),
        port=ctx.cfg.port,
        open_mode=settings.open_mode,
        dev_mode=ctx.cfg.dev_mode,
        run_mode=ctx.cfg.run_mode,
        started_at=ctx.started_at,
        python_version=platform.python_version(),
    )


def _open_in_explorer(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606 - 只打开本机数据目录
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607


@router.post("/system/open-folder", status_code=204, response_class=Response)
async def open_folder(body: OpenFolderRequest, ctx: AppContext = Depends(get_ctx)) -> Response:
    target = {"data": ctx.cfg.data_dir, "logs": ctx.cfg.logs_dir, "exports": ctx.cfg.exports_dir}[body.target]
    try:
        _open_in_explorer(target)
    except OSError as exc:
        logger.warning("打开目录失败：%s", exc)
        raise bad_request(f"打开目录失败：{exc}") from exc
    return Response(status_code=204)


@router.post("/system/shutdown", status_code=202, response_model=ShutdownResult)
async def shutdown(request: Request, background: BackgroundTasks, ctx: AppContext = Depends(get_ctx)) -> ShutdownResult:
    """暂停所有运行中的任务并退出程序：接口先返回，再通知启动器执行退出流程（07 第 5.1 节第 9 步）。
    开发模式下只暂停任务，不退出。"""
    paused = await ctx.manager.pause_all()
    if not ctx.cfg.dev_mode:
        callback = getattr(request.app.state, "exit_callback", None) or ctx.exit_callback
        # 后台任务在响应发出之后执行；同步函数由线程池调用（启动器的回调只让托盘循环结束）
        background.add_task(callback if callback is not None else _interrupt_self)
    return ShutdownResult(paused_jobs=paused)


def _interrupt_self() -> None:
    """直接用 uvicorn 运行、没有启动器时：向自己发送中断信号，让 uvicorn 正常收尾。"""
    import signal

    logger.info("收到退出请求，正在关闭")
    try:
        signal.raise_signal(signal.SIGINT)
    except (OSError, ValueError):
        os._exit(0)
