"""模型配置接口（04 第 4 节）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.schemas.common import ErrorResponse
from app.schemas.models import (
    ModelConfig,
    ModelConfigInput,
    ModelConfigList,
    ModelConfigPatch,
    ModelDraftRequest,
    ModelTestResult,
    RemoteModelList,
)
from app.services import model_service

router = APIRouter(prefix="/api", tags=["模型"], responses=ERROR_RESPONSES)


@router.get("/models", response_model=ModelConfigList)
async def list_models(
    include_demo: bool = Query(False, description="设置隐藏了演示模型时，传 true 强制包含"),
    ctx: AppContext = Depends(get_ctx),
) -> ModelConfigList:
    return ModelConfigList(items=await model_service.list_models(ctx.db, ctx.crypto, include_demo))


@router.post("/models", status_code=201, response_model=ModelConfig)
async def create_model(body: ModelConfigInput, ctx: AppContext = Depends(get_ctx)) -> ModelConfig:
    return await model_service.create_model(ctx.db, ctx.crypto, body)


@router.post("/models/test-draft", response_model=ModelTestResult)
async def test_model_draft(body: ModelDraftRequest, ctx: AppContext = Depends(get_ctx)) -> ModelTestResult:
    return await model_service.test_draft(ctx.db, ctx.crypto, ctx.llm, body)


@router.post(
    "/models/list-remote",
    response_model=RemoteModelList,
    responses={502: {"model": ErrorResponse, "description": "上游不支持或出错"}},
)
async def list_remote_models(body: ModelDraftRequest, ctx: AppContext = Depends(get_ctx)) -> RemoteModelList:
    return await model_service.list_remote(ctx.db, ctx.crypto, ctx.llm, body)


@router.get("/models/{id}", response_model=ModelConfig)
async def get_model(id: int, ctx: AppContext = Depends(get_ctx)) -> ModelConfig:
    return await model_service.get_model(ctx.db, ctx.crypto, id)


@router.patch("/models/{id}", response_model=ModelConfig)
async def update_model(id: int, body: ModelConfigPatch, ctx: AppContext = Depends(get_ctx)) -> ModelConfig:
    result = await model_service.update_model(ctx.db, ctx.crypto, id, body)
    ctx.manager.on_model_updated(id, result.concurrency_cap)
    return result


@router.delete("/models/{id}", status_code=204, response_class=Response)
async def delete_model(id: int, ctx: AppContext = Depends(get_ctx)) -> Response:
    await model_service.delete_model(ctx.db, id)
    return Response(status_code=204)


@router.post("/models/{id}/test", response_model=ModelTestResult)
async def test_model(id: int, ctx: AppContext = Depends(get_ctx)) -> ModelTestResult:
    return await model_service.test_saved(ctx.db, ctx.crypto, ctx.llm, id)
