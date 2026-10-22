"""设置接口（04 第 3.2 节）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.schemas.system import Settings, SettingsPatch
from app.services import settings_service

router = APIRouter(prefix="/api", tags=["设置"], responses=ERROR_RESPONSES)


@router.get("/settings", response_model=Settings)
async def get_settings(ctx: AppContext = Depends(get_ctx)) -> Settings:
    return await settings_service.get_settings(ctx.db)


@router.patch("/settings", response_model=Settings)
async def update_settings(body: SettingsPatch, ctx: AppContext = Depends(get_ctx)) -> Settings:
    return await settings_service.update_settings(ctx.db, body)
