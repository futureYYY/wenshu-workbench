"""迁移执行器（03 第 8 节）：PRAGMA user_version 记版本，按编号顺序执行 NNNN_说明.sql。

迁移在启动时用标准库 sqlite3 同步执行（在异步引擎打开之前），每个文件一个事务。
失败时记录日志、设置 last_error，并抛出 MigrationError，程序不继续启动，也不改动数据。
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# 最近一次迁移失败的说明，启动器据此提示“数据库升级失败”
last_error: str | None = None

_FILE_RE = re.compile(r"^(\d{4})_.+\.sql$")


class MigrationError(RuntimeError):
    pass


def list_migrations(migrations_dir: Path) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _FILE_RE.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    found.sort(key=lambda item: item[0])
    return found


def split_statements(sql: str) -> list[str]:
    """按 SQLite 自己的词法判断语句是否完整，注释里的分号不会误切。"""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            stmt = buffer.strip()
            if stmt and not _only_comments(stmt):
                statements.append(stmt)
            buffer = ""
    if buffer.strip() and not _only_comments(buffer.strip()):
        raise MigrationError("迁移文件末尾有不完整的语句")
    return statements


def _only_comments(stmt: str) -> bool:
    return all(not ln.strip() or ln.strip().startswith("--") for ln in stmt.splitlines())


def run_migrations(db_path: Path, migrations_dir: Path) -> tuple[int, int]:
    """执行未应用的迁移，返回 (迁移前版本, 迁移后版本)。"""
    global last_error
    last_error = None
    migrations = list_migrations(migrations_dir)
    if not migrations:
        last_error = f"没有找到迁移文件：{migrations_dir}"
        logger.error("数据库升级失败：%s", last_error)
        raise MigrationError(last_error)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not db_path.exists() or db_path.stat().st_size == 0
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        if is_new_file:
            # 03 第 2 节：新库文件的第一个连接必须先设 auto_vacuum，再切 WAL；
            # 顺序反过来时文件已经建好，auto_vacuum 实际仍为 0，删除任务后空间回收不了
            conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        before = int(conn.execute("PRAGMA user_version").fetchone()[0])
        current = before
        for number, path in migrations:
            if number <= current:
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                statements = split_statements(sql)
                conn.execute("BEGIN IMMEDIATE")
                for stmt in statements:
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {number}")
                conn.execute("COMMIT")
            except Exception as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                last_error = f"{path.name}：{exc}"
                logger.exception("数据库升级失败：%s", last_error)
                raise MigrationError(last_error) from exc
            logger.info("数据库已升级到版本 %d（%s）", number, path.name)
            current = number
        auto_vacuum = int(conn.execute("PRAGMA auto_vacuum").fetchone()[0])
        if auto_vacuum != 2:
            logger.warning("数据库的 auto_vacuum 为 %d（应为 2，即 INCREMENTAL），删除任务后空间不会自动回收", auto_vacuum)
        return before, current
    finally:
        conn.close()
