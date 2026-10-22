"""任务、条目、轨道、类别统计与实时事件（04 第 8、10 节）。"""

from __future__ import annotations

from typing import Any, Literal

from app.schemas.common import (
    ChatMessage,
    Concurrency,
    ItemStatus,
    JobStatus,
    JoinMode,
    KeyPoint,
    NonEmptyStrList,
    Retries,
    RowLimit,
    Schema,
    StatusReasonCode,
    TaskType,
    Usage,
    int_range,
    text_len,
)

ItemOrder = Literal[
    "seq", "-seq", "confidence", "-confidence", "latency_ms", "-latency_ms", "input_chars", "-input_chars"
]
TrackPhase = Literal["request", "waiting_retry", "chunk", "merge", "parse_repair"]
JobName = text_len(1, 100)
HeaderRow = int_range(0, 1_000_000)
StartRow = int_range(1, 10_000_000)
ManualLabel = text_len(1, 64)
ManualSummary = text_len(1, 10000)
ItemNote = text_len(0, 500)


class JobSourceInput(Schema):
    sheet: str | None
    header_row: HeaderRow
    text_columns: NonEmptyStrList
    join_mode: JoinMode = "labeled"
    start_row: StartRow | None = None
    limit: RowLimit | None
    split_mode: Literal["line"] = "line"


class JobCreate(Schema):
    name: JobName | None = None
    task_type: TaskType
    file_id: int
    source: JobSourceInput
    prompt_id: int
    model_id: int
    concurrency: Concurrency
    max_retries: Retries | None = None
    dedupe: bool | None = None


class JobEstimate(Schema):
    item_count: int
    skipped_empty: int
    duplicate_count: int
    request_count: int
    long_text_count: int
    est_prompt_tokens: int
    est_completion_tokens: int
    est_seconds: tuple[int, int]
    warnings: list[str]


class JobProgress(Schema):
    total: int
    pending: int
    running: int
    succeeded: int
    failed: int
    skipped: int
    percent: float
    rate_per_min: float | None
    eta_seconds: int | None


class JobSummary(Schema):
    id: int
    name: str
    task_type: TaskType
    status: JobStatus
    status_reason: str
    status_reason_code: StatusReasonCode | None
    file_name: str
    model_name: str
    prompt_name: str
    prompt_version: int
    concurrency: int
    progress: JobProgress
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str


class CategoryStat(Schema):
    label: str
    count: int
    percent: float
    color_index: int


class Compression(Schema):
    input_chars: int
    output_chars: int
    ratio: float | None


class JobLive(JobSummary):
    """实时推送用：JobSummary + 统计，不含快照。"""

    usage: Usage
    categories: list[CategoryStat] | None
    compression: Compression | None


class JobColumn(Schema):
    key: str
    title: str
    letter: str | None
    index: int


class JobSource(Schema):
    sheet: str | None
    header_row: int
    text_columns: list[str]
    join_mode: JoinMode
    start_row: int | None
    limit: int | None
    split_mode: Literal["line"]
    columns: list[JobColumn]


class Job(JobLive):
    file_id: int | None
    source: JobSource
    prompt_id: int | None
    prompt_snapshot: dict[str, Any]
    model_id: int | None
    model_snapshot: dict[str, Any]
    max_retries: int
    dedupe: bool
    label_options: list[str]    # 意图识别：提示词快照里列出的类别（05 第 4.6 节），人工修正只能改成这些；摘要任务为空


class JobPage(Schema):
    items: list[JobSummary]
    total: int


class JobPatch(Schema):
    name: JobName | None = None
    concurrency: Concurrency | None = None


class ItemSummary(Schema):
    id: int
    seq: int
    row_number: int
    status: ItemStatus
    input_preview: str
    input_chars: int
    label: str | None
    effective_label: str | None
    manual_label: str | None
    corrected: bool             # 意图或摘要有人工修正
    confidence: float | None
    reason: str | None
    summary_preview: str | None      # 有效摘要（人工修改过的取修改后的）前 200 字
    output_chars: int | None         # 有效摘要加要点的字数
    compression_ratio: float | None
    truncated: bool
    chunk_count: int
    attempts: int
    latency_ms: int | None
    error_code: str | None
    error_message: str | None
    reviewed: bool
    dedup_of: int | None
    finished_at: str | None


class ItemPage(Schema):
    items: list[ItemSummary]
    total: int


class AttemptLogEntry(Schema):
    at: str
    attempt: int
    phase: str
    status_code: int | None
    error_code: str | None
    message: str
    latency_ms: int | None


class ItemDetail(ItemSummary):
    input_text: str
    row_values: dict[str, str]
    segments: list[str] | None
    summary: str | None              # 模型输出的摘要主旨
    manual_summary: str | None       # 人工修改后的摘要主旨；没有修改为 null
    key_points: list[KeyPoint] | None
    result: dict[str, Any] | None
    raw_output: str | None
    reasoning: str | None
    messages: list[ChatMessage]
    omitted_chars: int | None
    attempt_log: list[AttemptLogEntry]
    model_used: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    note: str | None
    manual_at: str | None            # 最近一次人工修正的时间
    started_at: str | None


class ItemPatch(Schema):
    """人工复核（04 第 8.2 节）。manual_label、manual_summary 为 null 表示撤销修正；
    意图只能改成提示词里列出的类别，修正时自动标记已复核。"""

    manual_label: ManualLabel | None = None
    manual_summary: ManualSummary | None = None
    reviewed: bool | None = None
    note: ItemNote | None = None


class Track(Schema):
    item_id: int
    seq: int
    row_number: int
    input_preview: str
    started_at: str
    attempt: int
    phase: TrackPhase
    phase_detail: str
    retry_at: str | None


class TrackList(Schema):
    items: list[Track]


class CategoryList(Schema):
    items: list[CategoryStat]
    failed: int


# ---- SSE 事件数据（GET /api/events） ----


class ItemsUpdatedEvent(Schema):
    job_id: int
    items: list[ItemSummary]


class TracksUpdatedEvent(Schema):
    job_id: int
    items: list[Track]


class JobDeletedEvent(Schema):
    job_id: int


class PingEvent(Schema):
    """ping 事件的数据：空对象。"""
