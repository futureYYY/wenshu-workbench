"""条目、类别统计、并行轨道接口（04 第 8.2 节）。类别合并（categories/merge）是 P1，第一版不提供。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.schemas.jobs import CategoryList, ItemDetail, ItemOrder, ItemPage, ItemPatch, ItemSummary, TrackList
from app.services import job_service

router = APIRouter(prefix="/api", tags=["条目"], responses=ERROR_RESPONSES)


@router.get("/jobs/{id}/items", response_model=ItemPage)
async def list_items(
    id: int,
    status: str | None = Query(None, description="逗号分隔多个，如 failed,skipped"),
    label: list[str] | None = Query(None, description="按有效类别筛选，可重复传多个"),
    q: str | None = Query(None, description="关键词，匹配原文、类别、判断依据、摘要（含人工修改的摘要）"),
    reviewed: bool | None = Query(None, description="是否已复核"),
    corrected: bool | None = Query(None, description="意图或摘要是否有人工修正"),
    order: ItemOrder = Query("seq"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    ctx: AppContext = Depends(get_ctx),
) -> ItemPage:
    filters = job_service.build_filters(status, label, q, reviewed, corrected)
    return await job_service.list_items(ctx, id, filters, order=order, offset=offset, limit=limit)


@router.get("/jobs/{id}/items/{item_id}", response_model=ItemDetail)
async def get_item(id: int, item_id: int, ctx: AppContext = Depends(get_ctx)) -> ItemDetail:
    return await job_service.get_item(ctx, id, item_id)


@router.patch("/jobs/{id}/items/{item_id}", response_model=ItemSummary)
async def update_item(id: int, item_id: int, body: ItemPatch, ctx: AppContext = Depends(get_ctx)) -> ItemSummary:
    return await job_service.patch_item(ctx, id, item_id, body)


@router.post("/jobs/{id}/items/{item_id}/rerun", response_model=ItemSummary)
async def rerun_item(id: int, item_id: int, ctx: AppContext = Depends(get_ctx)) -> ItemSummary:
    await ctx.manager.rerun_item(id, item_id)
    return await job_service.item_summary_by_id(ctx, id, item_id)


@router.get("/jobs/{id}/categories", response_model=CategoryList)
async def get_categories(id: int, ctx: AppContext = Depends(get_ctx)) -> CategoryList:
    return await job_service.get_categories(ctx, id)


@router.get("/jobs/{id}/tracks", response_model=TrackList)
async def get_tracks(id: int, ctx: AppContext = Depends(get_ctx)) -> TrackList:
    return TrackList(items=await job_service.get_tracks(ctx, id))
