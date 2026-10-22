"""系统与设置（04 第 3 节）。"""

from __future__ import annotations

from typing import Literal

from app.schemas.common import Concurrency, Port, Retries, RowLimit, Schema

Theme = Literal["system", "light", "dark"]
OpenMode = Literal["app", "browser"]


class Health(Schema):
    status: Literal["ok"]
    version: str


class SystemInfo(Schema):
    version: str
    data_dir: str
    port: int
    open_mode: OpenMode
    dev_mode: bool
    run_mode: Literal["exe", "source", "dev"]
    started_at: str
    python_version: str


class OpenFolderRequest(Schema):
    target: Literal["data", "logs", "exports"]


class ShutdownResult(Schema):
    paused_jobs: int


class TaskConcurrency(Schema):
    classify: int
    summarize: int


class TaskModelIds(Schema):
    classify: int | None
    summarize: int | None


class TaskPromptIds(Schema):
    classify: int
    summarize: int


class SettingsLimits(Schema):
    max_concurrency: int
    max_rows_per_source: int
    max_upload_bytes: int


class Settings(Schema):
    default_concurrency: TaskConcurrency
    default_limit: int | None
    default_max_retries: int
    default_dedupe: bool
    default_model_id: TaskModelIds
    default_prompt_id: TaskPromptIds
    theme: Theme
    open_mode: OpenMode
    preferred_port: int
    show_demo_model: bool
    limits: SettingsLimits


class TaskConcurrencyPatch(Schema):
    classify: Concurrency | None = None
    summarize: Concurrency | None = None


class TaskModelIdsPatch(Schema):
    classify: int | None = None
    summarize: int | None = None


class TaskPromptIdsPatch(Schema):
    classify: int | None = None
    summarize: int | None = None


class SettingsPatch(Schema):
    """部分更新：只传要改的项，嵌套对象也可以只传其中一项。"""

    default_concurrency: TaskConcurrencyPatch | None = None
    default_limit: RowLimit | None = None
    default_max_retries: Retries | None = None
    default_dedupe: bool | None = None
    default_model_id: TaskModelIdsPatch | None = None
    default_prompt_id: TaskPromptIdsPatch | None = None
    theme: Theme | None = None
    open_mode: OpenMode | None = None
    preferred_port: Port | None = None
    show_demo_model: bool | None = None
