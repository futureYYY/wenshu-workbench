"""试运行接口（04 第 6 节）：POST /api/playground/run，返回 text/event-stream。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.schemas.prompts import PlaygroundRunRequest
from app.services import playground_service

router = APIRouter(prefix="/api", tags=["试运行"], responses=ERROR_RESPONSES)


@router.post(
    "/playground/run",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "事件流：stage、delta、reasoning_delta、done、error（数据结构见 PlaygroundStageEvent、PlaygroundDeltaEvent、PlaygroundDone、PlaygroundErrorEvent）",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def run_playground(body: PlaygroundRunRequest, ctx: AppContext = Depends(get_ctx)) -> EventSourceResponse:
    return EventSourceResponse(playground_service.run(ctx, body), ping=15, headers={"Cache-Control": "no-cache"})
