"""开发模式专用接口（04 第 3.1 节）：只在 WENSHU_DEV=1 时注册，供端到端测试和后端测试在每个用例前重置数据。"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ERROR_RESPONSES
from app.context import AppContext, get_ctx
from app.db.models import (
    FileRow,
    JobItemRow,
    JobRow,
    ModelConfigRow,
    PromptTemplateRow,
    PromptVersionRow,
    SettingRow,
)
from app.db.seed import run_seed
from app.services.job_engine.limiter import ModelLimiters
from app.services.job_engine.writer import ResultWriter, WriteOp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/_dev", tags=["开发"], responses=ERROR_RESPONSES)


def _clear_dir(path: Path) -> None:
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


@router.post("/reset", status_code=204, response_class=Response)
async def dev_reset(ctx: AppContext = Depends(get_ctx)) -> Response:
    """停止全部任务；清空任务、条目、文件、提示词（内置的随后按默认内容重建）、演示模型以外的模型；
    设置恢复默认；重新执行启动初始化（03 第 8 节，按新库处理，默认自定义模型的占位条目也会重建）；
    重置演示模型的统计。"""
    await ctx.manager.stop_all()
    ctx.manager.model_limiters = ModelLimiters()

    async def apply(session: AsyncSession, _w: ResultWriter, _op: WriteOp) -> None:
        await session.execute(delete(JobItemRow))
        await session.execute(delete(JobRow))
        await session.execute(delete(FileRow))
        await session.execute(delete(PromptVersionRow))
        await session.execute(delete(PromptTemplateRow))
        await session.execute(delete(ModelConfigRow).where(ModelConfigRow.provider_kind != "demo"))
        await session.execute(delete(SettingRow))

    await ctx.writer.run(apply, job_event="none")
    ctx.writer.forget_all()
    ctx.previews.clear()
    await asyncio.to_thread(_clear_dir, ctx.cfg.uploads_dir)
    await asyncio.to_thread(_clear_dir, ctx.cfg.exports_dir)
    await run_seed(ctx.db, ctx.crypto, ctx.cfg.models_file, fresh_db=True)
    await ctx.llm.close_all()
    ctx.mock.reset()
    logger.info("开发模式：数据已重置")
    return Response(status_code=204)
