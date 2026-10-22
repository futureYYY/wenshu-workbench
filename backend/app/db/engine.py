"""异步引擎与连接设置（03 第 2 节）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import URL, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

CONNECT_PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA temp_store = MEMORY",
)


def _on_connect(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        for pragma in CONNECT_PRAGMAS:
            cursor.execute(pragma)
    finally:
        cursor.close()


class Database:
    """持有异步引擎和会话工厂。读操作各自开会话（独立连接），写入集中在写入协程里。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        # 用 URL.create 构造，路径里有中文、空格或 #、? 等字符时也不会被当成 URL 解析
        url = URL.create("sqlite+aiosqlite", database=str(db_path))
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_size=10,
            max_overflow=10,
            pool_pre_ping=False,
        )
        event.listen(self.engine.sync_engine, "connect", _on_connect)
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )

    def session(self) -> AsyncSession:
        return self.sessionmaker()

    async def dispose(self) -> None:
        await self.engine.dispose()
