"""文件接口（04 第 7 节）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.schemas.common import ErrorResponse
from app.schemas.files import FileInfo, FilePage, FilePreview, PasteRequest
from app.services import file_service

router = APIRouter(prefix="/api", tags=["文件"], responses=ERROR_RESPONSES)


@router.post(
    "/files",
    status_code=201,
    response_model=FileInfo,
    responses={
        200: {"model": FileInfo, "description": "内容与已有文件相同，直接复用（reused 为 true）"},
        413: {"model": ErrorResponse, "description": "文件超过 50 MB"},
        415: {"model": ErrorResponse, "description": "扩展名不支持"},
    },
)
async def upload_file(response: Response, file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)) -> FileInfo:
    info, created = await file_service.upload(ctx, file.filename or "", file.file)
    if not created:
        response.status_code = 200
    return info


@router.post(
    "/files/paste",
    status_code=201,
    response_model=FileInfo,
    responses={200: {"model": FileInfo, "description": "内容与已有文件相同，直接复用（reused 为 true）"}},
)
async def paste_text(body: PasteRequest, response: Response, ctx: AppContext = Depends(get_ctx)) -> FileInfo:
    info, created = await file_service.paste(ctx, body.text, body.name)
    if not created:
        response.status_code = 200
    return info


@router.get("/files", response_model=FilePage)
async def list_files(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    ctx: AppContext = Depends(get_ctx),
) -> FilePage:
    return await file_service.list_files(ctx, offset, limit)


@router.get("/files/{id}", response_model=FileInfo)
async def get_file(id: int, ctx: AppContext = Depends(get_ctx)) -> FileInfo:
    return await file_service.get_file(ctx, id)


@router.get("/files/{id}/preview", response_model=FilePreview)
async def preview_file(
    id: int,
    sheet: str | None = Query(None, description="表格类必填；不传时取第一个工作表"),
    header_row: int = Query(1, ge=0, description="表头所在行号，0 表示无表头；lines 类忽略"),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    ctx: AppContext = Depends(get_ctx),
) -> FilePreview:
    return await file_service.preview(ctx, id, sheet, header_row, offset, limit)


@router.delete("/files/{id}", status_code=204, response_class=Response)
async def delete_file(id: int, ctx: AppContext = Depends(get_ctx)) -> Response:
    await file_service.delete_file(ctx, id)
    return Response(status_code=204)
