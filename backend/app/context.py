"""应用上下文：生命周期里创建的共享对象，路由通过 Depends(get_ctx) 取得。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.api.mock import MockState
    from app.config import AppConfig
    from app.db.engine import Database
    from app.services.crypto import Crypto
    from app.services.event_bus import EventBus
    from app.services.file_parser import PreviewCache
    from app.services.job_engine.manager import JobManager
    from app.services.job_engine.writer import ResultWriter
    from app.services.llm_client import LLMClients


@dataclass
class AppContext:
    cfg: AppConfig
    db: Database
    crypto: Crypto
    bus: EventBus
    llm: LLMClients
    writer: ResultWriter
    manager: JobManager
    mock: MockState
    previews: PreviewCache
    started_at: str
    exit_callback: Callable[[], None] | None = None
    extra: dict[str, object] = field(default_factory=dict)


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
