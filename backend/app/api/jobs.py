"""任务接口（04 第 8.1 节）。固定路径（estimate）写在 /{id} 之前。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.schemas.common import TaskType
from app.schemas.jobs import Job, JobCreate, JobEstimate, JobPage, JobPatch
from app.services import job_builder, job_service

router = APIRouter(prefix="/api", tags=["任务"], responses=ERROR_RESPONSES)


@router.post("/jobs/estimate", response_model=JobEstimate)
async def estimate_job(body: JobCreate, ctx: AppContext = Depends(get_ctx)) -> JobEstimate:
    return await job_builder.estimate(ctx, body)


@router.post("/jobs", status_code=201, response_model=Job)
async def create_job(body: JobCreate, ctx: AppContext = Depends(get_ctx)) -> Job:
    job_id = await job_builder.create(ctx, body)
    return await job_service.get_job(ctx, job_id)


@router.get("/jobs", response_model=JobPage)
async def list_jobs(
    status: str | None = Query(None, description="逗号分隔多个，如 running,paused"),
    task_type: TaskType | None = Query(None),
    q: str | None = Query(None, description="搜任务名和文件名"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    ctx: AppContext = Depends(get_ctx),
) -> JobPage:
    return await job_service.list_jobs(ctx, status=status, task_type=task_type, q=q, offset=offset, limit=limit)


@router.get("/jobs/{id}", response_model=Job)
async def get_job(id: int, ctx: AppContext = Depends(get_ctx)) -> Job:
    return await job_service.get_job(ctx, id)


@router.patch("/jobs/{id}", response_model=Job)
async def update_job(id: int, body: JobPatch, ctx: AppContext = Depends(get_ctx)) -> Job:
    return await job_service.patch_job(ctx, id, body)


@router.post("/jobs/{id}/pause", response_model=Job)
async def pause_job(id: int, ctx: AppContext = Depends(get_ctx)) -> Job:
    await ctx.manager.pause(id)
    return await job_service.get_job(ctx, id)


@router.post("/jobs/{id}/resume", response_model=Job)
async def resume_job(id: int, ctx: AppContext = Depends(get_ctx)) -> Job:
    await ctx.manager.resume(id)
    return await job_service.get_job(ctx, id)


@router.post("/jobs/{id}/cancel", response_model=Job)
async def cancel_job(id: int, ctx: AppContext = Depends(get_ctx)) -> Job:
    await ctx.manager.cancel(id)
    return await job_service.get_job(ctx, id)


@router.post("/jobs/{id}/retry-failed", response_model=Job)
async def retry_failed_items(id: int, ctx: AppContext = Depends(get_ctx)) -> Job:
    await ctx.manager.retry_failed(id)
    return await job_service.get_job(ctx, id)


@router.delete("/jobs/{id}", status_code=204, response_class=Response)
async def delete_job(id: int, ctx: AppContext = Depends(get_ctx)) -> Response:
    await ctx.manager.delete_job(id)
    return Response(status_code=204)
