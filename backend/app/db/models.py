"""SQLAlchemy 模型，与 03 第 3 节的表一一对应。

表结构由迁移文件创建（不使用 create_all），这里只用于查询和写入。布尔字段在库里是 INTEGER 0/1。
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ModelConfigRow(Base):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider_kind: Mapped[str] = mapped_column(Text, nullable=False, default="openai_compatible")
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    api_key_last4: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    max_tokens_param: Mapped[str] = mapped_column(Text, nullable=False, default="max_tokens")
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=32768)
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    concurrency_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    json_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    proxy_url: Mapped[str | None] = mapped_column(Text)
    extra_headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    extra_body_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_test_at: Mapped[str | None] = mapped_column(Text)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_latency_ms: Mapped[int | None] = mapped_column(Integer)
    last_test_message: Mapped[str | None] = mapped_column(Text)
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class PromptTemplateRow(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_template: Mapped[str | None] = mapped_column(Text)
    merge_template: Mapped[str | None] = mapped_column(Text)
    output_mode: Mapped[str] = mapped_column(Text, nullable=False, default="json")
    field_map_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    temperature: Mapped[float | None] = mapped_column(Float)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    builtin_key: Mapped[str | None] = mapped_column(Text, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class PromptVersionRow(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class FileRow(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    ext: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="upload")
    encoding: Mapped[str | None] = mapped_column(Text)
    delimiter: Mapped[str | None] = mapped_column(Text)
    meta_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[str] = mapped_column(Text, nullable=False)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status_reason_code: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("files.id", ondelete="SET NULL"))
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_json: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("prompt_templates.id", ondelete="SET NULL")
    )
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("model_configs.id", ondelete="SET NULL"))
    model_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    dedupe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_colors_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    category_aliases_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class JobItemRow(Base):
    __tablename__ = "job_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    row_values_json: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_of: Mapped[int | None] = mapped_column(Integer, ForeignKey("job_items.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_used: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    key_points_json: Mapped[str | None] = mapped_column(Text)
    output_chars: Mapped[int | None] = mapped_column(Integer)
    result_json: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    omitted_chars: Mapped[int | None] = mapped_column(Integer)
    render_meta_json: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_log_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    manual_label: Mapped[str | None] = mapped_column(Text)
    manual_summary: Mapped[str | None] = mapped_column(Text)      # 0002 迁移新增
    manual_at: Mapped[str | None] = mapped_column(Text)           # 0002 迁移新增
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text)
