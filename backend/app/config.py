"""路径、环境变量、常量与日志（02 第 9 节、03 第 5 节）。"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from app import APP_ID

# ---- 代码常量（03 第 5 节，不可设置） ----
MAX_CONCURRENCY = 20
MAX_ROWS_PER_SOURCE = 100_000
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
RAW_OUTPUT_MAX_CHARS = 100_000
REASONING_MAX_CHARS = 20_000

DEFAULT_PORT = 18765
DEMO_BASE_URL = "demo://local"
DEMO_MODEL_NAME = "wenshu-demo"
# 首次启动时生成的“默认自定义模型”占位条目使用的地址（RFC 2606 保留域名，只是占位）
PLACEHOLDER_BASE_URL = "https://api.example.com/v1"
PLACEHOLDER_MODEL = "your-model-name"

RunMode = Literal["exe", "source", "dev"]

logger = logging.getLogger(__name__)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_app_dir() -> Path:
    """程序目录：打包版为 exe 所在目录；源码版、开发为 backend/。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_bundle_dir() -> Path:
    """随程序分发的资源根目录：打包版为 sys._MEIPASS（_internal）；源码版为 backend/。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", resolve_app_dir()))
    return Path(__file__).resolve().parent.parent


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write-test-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_data_dir(app_dir: Path) -> Path:
    """按顺序取：WENSHU_DATA_DIR；app_dir/data（可写时）；%LOCALAPPDATA%\\WenShu\\data。"""
    env = os.environ.get("WENSHU_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    candidate = app_dir / "data"
    if _writable(candidate):
        return candidate.resolve()
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return (base / APP_ID / "data").resolve()


def resolve_run_mode() -> RunMode:
    if is_frozen():
        return "exe"
    if os.environ.get("WENSHU_DEV") == "1":
        return "dev"
    return "source"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass
class AppConfig:
    app_dir: Path
    bundle_dir: Path
    data_dir: Path
    run_mode: RunMode
    port: int
    mock_fail_rate: float
    log_level: str
    log_content: bool          # 只有显式设置 WENSHU_LOG_LEVEL=DEBUG 时才记录消息内容的前 200 字
    cors_origins: list[str]
    models_file: Path          # 默认自定义模型的本机配置文件（不提交，见 backend/README.md）

    @property
    def dev_mode(self) -> bool:
        return self.run_mode == "dev"

    @property
    def static_dir(self) -> Path:
        return self.bundle_dir / "app" / "static"

    @property
    def migrations_dir(self) -> Path:
        return self.bundle_dir / "app" / "db" / "migrations"

    @property
    def swagger_dir(self) -> Path:
        """/docs 用的 Swagger UI 静态文件（02 第 2.2 节），随后端分发。"""
        return self.bundle_dir / "app" / "vendor" / "swagger-ui"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "wenshu.db"

    @property
    def secret_key_file(self) -> Path:
        return self.data_dir / "secret.key"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def browser_dir(self) -> Path:
        return self.data_dir / "browser"

    @property
    def runtime_file(self) -> Path:
        return self.data_dir / "runtime.json"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.exports_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_config(*, data_dir: Path | None = None, port: int | None = None) -> AppConfig:
    app_dir = resolve_app_dir()
    run_mode = resolve_run_mode()
    explicit_level = os.environ.get("WENSHU_LOG_LEVEL", "").strip().upper()
    level = explicit_level or ("DEBUG" if run_mode == "dev" else "INFO")
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = "INFO"
    cors = [o.strip().rstrip("/") for o in os.environ.get("WENSHU_CORS_ORIGINS", "").split(",") if o.strip()]
    models_file_env = os.environ.get("WENSHU_MODELS_FILE", "").strip()
    return AppConfig(
        app_dir=app_dir,
        bundle_dir=resolve_bundle_dir(),
        data_dir=Path(data_dir).resolve() if data_dir else resolve_data_dir(app_dir),
        run_mode=run_mode,
        port=port if port is not None else _env_int("WENSHU_PORT", DEFAULT_PORT),
        mock_fail_rate=min(1.0, max(0.0, _env_float("WENSHU_MOCK_FAIL_RATE", 0.02))),
        log_level=level,
        log_content=explicit_level == "DEBUG",
        cors_origins=cors,
        models_file=Path(models_file_env) if models_file_env else app_dir / "models.local.json",
    )


_NOISY_LOGGERS = (
    "httpx", "httpx2", "httpcore", "httpcore2", "openai", "aiosqlite",
    "sqlalchemy.engine", "multipart", "python_multipart", "PIL", "sse_starlette",
)


def setup_logging(cfg: AppConfig) -> None:
    """标准库 logging：data/logs/app.log，单个 5 MB，保留 5 个。可重复调用。"""
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_wenshu", False):
            root.removeHandler(handler)
            handler.close()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        cfg.logs_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler._wenshu = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    # 窗口程序（pythonw、打包版）没有控制台，sys.stderr 为 None，只写文件
    if sys.stderr is not None and not is_frozen():
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console._wenshu = True  # type: ignore[attr-defined]
        root.addHandler(console)
    root.setLevel(cfg.log_level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
