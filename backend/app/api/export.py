"""导出接口（04 第 9 节）：GET /api/jobs/{id}/export?format=xlsx&scope=all。"""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.db.repo.items import ItemFilters
from app.services import exporter, job_service

router = APIRouter(prefix="/api", tags=["导出"], responses=ERROR_RESPONSES)


@router.get(
    "/jobs/{id}/export",
    response_class=Response,
    responses={
        200: {
            "description": "导出文件（Content-Disposition 里是 UTF-8 编码的文件名）",
            "content": {exporter.MEDIA_TYPES["xlsx"]: {}, "text/csv": {}},
        }
    },
)
async def export_job(
    id: int,
    format: Literal["xlsx", "csv"] = Query("xlsx"),
    scope: Literal["all", "filtered"] = Query("all"),
    status: str | None = Query(None),
    label: list[str] | None = Query(None),
    q: str | None = Query(None),
    reviewed: bool | None = Query(None),
    corrected: bool | None = Query(None),
    ctx: AppContext = Depends(get_ctx),
) -> Response:
    filters = job_service.build_filters(status, label, q, reviewed, corrected) if scope == "filtered" else ItemFilters()
    path, name = await exporter.export_job(ctx, id, format, filters, scope)
    return FileResponse(
        path,
        media_type=exporter.MEDIA_TYPES[format],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
