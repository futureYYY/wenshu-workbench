"""提示词接口（04 第 5 节）。固定路径（variables、render）写在 /{id} 之前。"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, Response

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.schemas.common import TaskType
from app.schemas.prompts import (
    PromptCopy,
    PromptInput,
    PromptRestoreRequest,
    PromptTemplate,
    PromptTemplateList,
    PromptVariableList,
    PromptVersionDetail,
    PromptVersionList,
    RenderRequest,
    RenderResult,
)
from app.services import prompt_service

router = APIRouter(prefix="/api", tags=["提示词"], responses=ERROR_RESPONSES)


@router.get("/prompts", response_model=PromptTemplateList)
async def list_prompts(
    task_type: TaskType | None = Query(None), ctx: AppContext = Depends(get_ctx)
) -> PromptTemplateList:
    return PromptTemplateList(items=await prompt_service.list_prompts(ctx.db, task_type))


@router.post("/prompts", status_code=201, response_model=PromptTemplate)
async def create_prompt(
    body: PromptInput | PromptCopy = Body(..., description="新建（PromptInput）或复制（{copy_from_id, name?}）"),
    ctx: AppContext = Depends(get_ctx),
) -> PromptTemplate:
    return await prompt_service.create_prompt(ctx.db, body)


@router.get("/prompts/variables", response_model=PromptVariableList)
async def list_prompt_variables(task_type: TaskType = Query(...)) -> PromptVariableList:
    return PromptVariableList(items=prompt_service.list_variables(task_type))


@router.post("/prompts/render", response_model=RenderResult)
async def render_prompt(body: RenderRequest, ctx: AppContext = Depends(get_ctx)) -> RenderResult:
    return await prompt_service.render(ctx, body)


@router.get("/prompts/{id}", response_model=PromptTemplate)
async def get_prompt(id: int, ctx: AppContext = Depends(get_ctx)) -> PromptTemplate:
    return await prompt_service.get_prompt(ctx.db, id)


@router.put("/prompts/{id}", response_model=PromptTemplate)
async def save_prompt(id: int, body: PromptInput, ctx: AppContext = Depends(get_ctx)) -> PromptTemplate:
    return await prompt_service.save_prompt(ctx.db, id, body)


@router.delete("/prompts/{id}", status_code=204, response_class=Response)
async def delete_prompt(id: int, ctx: AppContext = Depends(get_ctx)) -> Response:
    await prompt_service.delete_prompt(ctx.db, id)
    return Response(status_code=204)


@router.get("/prompts/{id}/versions", response_model=PromptVersionList)
async def list_prompt_versions(id: int, ctx: AppContext = Depends(get_ctx)) -> PromptVersionList:
    return PromptVersionList(items=await prompt_service.list_versions(ctx.db, id))


@router.get("/prompts/{id}/versions/{version}", response_model=PromptVersionDetail)
async def get_prompt_version(id: int, version: int, ctx: AppContext = Depends(get_ctx)) -> PromptVersionDetail:
    return await prompt_service.get_version(ctx.db, id, version)


@router.post("/prompts/{id}/restore", response_model=PromptTemplate)
async def restore_prompt_version(
    id: int, body: PromptRestoreRequest, ctx: AppContext = Depends(get_ctx)
) -> PromptTemplate:
    return await prompt_service.restore_version(ctx.db, id, body.version)


@router.post("/prompts/{id}/reset-builtin", response_model=PromptTemplate)
async def reset_builtin_prompt(id: int, ctx: AppContext = Depends(get_ctx)) -> PromptTemplate:
    return await prompt_service.reset_builtin(ctx.db, id)
