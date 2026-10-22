"""create_app()：组装应用（02 第 4 节）。模块级的 app 供 `uvicorn app.main:app` 使用。

生命周期启动时：执行迁移、初始化数据（03 第 8 节）、启动写入协程和 JobManager，并把事件循环和 JobManager
放在 app.state 上交给启动器（07 第 5.1 节第 4、9 步）；
关闭时：执行 02 第 5.7 节第 1–3、5 步（暂停全部任务、等进行中的请求、提交写入队列、关闭模型客户端和数据库连接），
重复执行没有副作用。结束事件流（第 4 步）由启动器在停 uvicorn 之前做。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic import TypeAdapter

from app import APP_NAME, __version__
from app.api import dev as dev_api
from app.api import docs as docs_api
from app.api import events as events_api
from app.api import export as export_api
from app.api import files as files_api
from app.api import items as items_api
from app.api import jobs as jobs_api
from app.api import mock as mock_api
from app.api import models as models_api
from app.api import playground as playground_api
from app.api import prompts as prompts_api
from app.api import settings as settings_api
from app.api import system as system_api
from app.api.errors import register_error_handlers
from app.api.mock import MockState
from app.api.static import build_static_router
from app.config import AppConfig, load_config, setup_logging
from app.context import AppContext
from app.db.engine import Database
from app.db.migrate import run_migrations
from app.db.seed import clean_exports, run_seed
from app.schemas import EXTRA_OPENAPI_MODELS
from app.security import CLIENT_HEADER, LocalOnlyMiddleware
from app.services.crypto import Crypto
from app.services.event_bus import EventBus
from app.services.file_parser import PreviewCache
from app.services.file_service import cleanup_tmp
from app.services.job_engine.manager import JobManager
from app.services.job_engine.writer import ResultWriter
from app.services.llm_client import LLMClients
from app.utils import now_iso

logger = logging.getLogger(__name__)

SECURITY_SCHEME = "WenShuClient"


class PortHolder:
    """服务实际监听的端口：启动器、开发脚本通过 WENSHU_PORT 传入；直接用 uvicorn 换了端口时由中间件从请求里更正。
    任务引擎调用演示模型时用它拼出 http://127.0.0.1:{端口}/mock/v1。"""

    def __init__(self, port: int) -> None:
        self.port = port


def _unique_id(route: APIRoute) -> str:
    """OpenAPI 的 operationId 用路由函数名，生成的前端类型更易读。"""
    return route.name


def _install_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            separate_input_output_schemas=False,
        )
        # 04 第 10.1 节：SSE 和试运行的事件数据不出现在普通接口的响应里，显式登记到 components.schemas
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        for model in EXTRA_OPENAPI_MODELS:
            definition = TypeAdapter(model).json_schema(
                ref_template="#/components/schemas/{model}", mode="serialization"
            )
            for name, sub in definition.pop("$defs", {}).items():
                schemas.setdefault(name, sub)
            schemas.setdefault(model.__name__, definition)
        # 02 第 10 节：声明 apiKey 安全方案，只为让 /docs 出现 Authorize 按钮；真正的检查由中间件做
        components.setdefault("securitySchemes", {})[SECURITY_SCHEME] = {
            "type": "apiKey",
            "in": "header",
            "name": CLIENT_HEADER,
            "description": "除 GET 外的 /api 请求都要带这个请求头，值为 1",
        }
        schema["security"] = [{SECURITY_SCHEME: []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app(
    *,
    data_dir: Path | None = None,
    port: int | None = None,
    exit_callback: Callable[[], None] | None = None,
) -> FastAPI:
    """create_app 本身很轻：迁移、初始化和任务引擎都在 lifespan 里启动。"""
    cfg: AppConfig = load_config(data_dir=data_dir, port=port)
    port_holder = PortHolder(cfg.port)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg.ensure_dirs()
        setup_logging(cfg)
        logger.info(
            "%s %s 启动：运行方式 %s，数据目录 %s，端口 %d", APP_NAME, __version__, cfg.run_mode, cfg.data_dir, cfg.port
        )
        before, _after = await asyncio.to_thread(run_migrations, cfg.db_path, cfg.migrations_dir)
        db = Database(cfg.db_path)
        crypto = Crypto(cfg.secret_key_file)
        await run_seed(db, crypto, cfg.models_file, fresh_db=before == 0)
        clean_exports(cfg.exports_dir)
        cleanup_tmp(cfg.uploads_dir)

        bus = EventBus()
        llm = LLMClients(lambda: port_holder.port, log_content=cfg.log_content)
        writer = ResultWriter(db, bus)
        writer.start()
        manager = JobManager(cfg=cfg, db=db, bus=bus, writer=writer, llm=llm, crypto=crypto)
        # 07 第 5.1 节第 4 步：事件循环和 JobManager 交给启动器保存，退出时它在主线程里调度 shutdown()
        app.state.loop = asyncio.get_running_loop()
        app.state.job_manager = manager
        app.state.ctx = AppContext(
            cfg=cfg,
            db=db,
            crypto=crypto,
            bus=bus,
            llm=llm,
            writer=writer,
            manager=manager,
            mock=MockState(cfg.mock_fail_rate),
            previews=PreviewCache(),
            started_at=now_iso(),
            exit_callback=exit_callback,
        )
        try:
            yield
        finally:
            try:
                await manager.shutdown()
            except Exception:  # noqa: BLE001 - 退出流程不能中断
                logger.exception("退出时暂停任务失败")
            await writer.stop()
            await llm.close_all()
            await db.dispose()
            logger.info("%s 已退出", APP_NAME)

    app = FastAPI(
        title=f"{APP_NAME} WenShu 接口",
        version=__version__,
        description=(
            "文枢后端接口。除 GET、OPTIONS 外的 /api 请求需要请求头 X-WenShu-Client: 1"
            "（调试时先点 Authorize 填 1）；只接受本机地址访问。"
        ),
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        generate_unique_id_function=_unique_id,
        separate_input_output_schemas=False,
    )
    app.state.cfg = cfg
    app.state.port_holder = port_holder
    app.state.exit_callback = exit_callback
    app.state.loop = None
    app.state.job_manager = None
    register_error_handlers(app)

    for router in (
        system_api.router,
        settings_api.router,
        models_api.router,
        prompts_api.router,
        playground_api.router,
        files_api.router,
        jobs_api.router,
        items_api.router,
        export_api.router,
        events_api.router,
        mock_api.router,
        docs_api.router,
    ):
        app.include_router(router)
    if cfg.dev_mode:
        # 04 第 3.1 节：只在开发模式注册，供端到端测试和后端测试重置数据
        app.include_router(dev_api.router)
    # 静态文件和 SPA 回退放在最后
    app.include_router(build_static_router(cfg.static_dir))

    app.add_middleware(LocalOnlyMiddleware, port_holder=port_holder)
    if cfg.cors_origins:
        # 前端单独部署时才放行列出的来源（02 第 10 节）。Starlette 里最后 add_middleware 的在最外层：
        # CORSMiddleware 必须最后加，跨来源的预检请求先由它应答，不会被 LocalOnlyMiddleware 拦下
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Content-Disposition"],
        )
    _install_openapi(app)
    return app


app = create_app()
