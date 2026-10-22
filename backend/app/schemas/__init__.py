"""请求和响应模型，字段与 docs/04-api.md 完全一致。"""

from app.schemas.common import (
    ChatMessage,
    ClassifyResult,
    ErrorBody,
    ErrorResponse,
    KeyPoint,
    SummarizeResult,
    Usage,
)
from app.schemas.jobs import (
    ItemsUpdatedEvent,
    JobDeletedEvent,
    JobLive,
    JobSummary,
    PingEvent,
    TracksUpdatedEvent,
)
from app.schemas.prompts import (
    PlaygroundDeltaEvent,
    PlaygroundDone,
    PlaygroundErrorEvent,
    PlaygroundStageEvent,
)

# 04 第 10.1 节：SSE 和试运行的事件数据不出现在普通接口的响应里，FastAPI 默认不会写进 OpenAPI。
# main.py 把它们显式登记到 components.schemas，npm run gen:api 会一起生成，前端不手写这些类型。
EXTRA_OPENAPI_MODELS = (
    JobSummary,             # 全局 job.created、job.updated
    JobLive,                # 单任务 job.updated
    JobDeletedEvent,        # job.deleted
    ItemsUpdatedEvent,      # items.updated
    TracksUpdatedEvent,     # tracks.updated
    PingEvent,              # ping
    PlaygroundStageEvent,   # 试运行 stage
    PlaygroundDeltaEvent,   # 试运行 delta、reasoning_delta
    PlaygroundDone,         # 试运行 done
    PlaygroundErrorEvent,   # 试运行 error
    ClassifyResult,
    SummarizeResult,
    KeyPoint,
    Usage,
    ChatMessage,
    ErrorBody,
    ErrorResponse,
)

__all__ = ["EXTRA_OPENAPI_MODELS"]
