"""实时事件（04 第 10 节、02 第 7 节）。

- GET /api/events：全局流，job.created、job.updated（JobSummary）、job.deleted、ping；
- GET /api/events?job_id=：单任务流，job.updated（JobLive）、items.updated、tracks.updated、ping。

单任务流按 250 毫秒窗口合并：同一条目多次更新只发最后一次，轨道只发最新状态，job.updated 每秒最多一次
（状态变化时立即发）。id 单调递增，服务端不做断线补发；客户端重连后重新拉取数据。

ping 由 sse-starlette 每 15 秒发送。它默认发的是注释行，前端监听不到，用 ping_message_factory 改成具名事件
（event: ping，data: {}）。程序退出时由启动器设置 AppStatus.should_exit 统一结束所有事件流（02 第 5.7 节第 4 步）。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.api.errors import ERROR_RESPONSES, not_found
from app.context import AppContext, get_ctx
from app.db.repo import jobs as jobs_repo
from app.services import job_service
from app.services.event_bus import (
    ITEMS_CHANGED,
    JOB_CHANGED,
    JOB_CREATED,
    JOB_DELETED,
    TRACKS_CHANGED,
    BusEvent,
    Subscriber,
)

router = APIRouter(prefix="/api", tags=["事件"], responses=ERROR_RESPONSES)

WINDOW = 0.25
JOB_INTERVAL = 1.0
PING_INTERVAL = 15
IDLE_WAIT = 30.0
ITEMS_PER_EVENT = 200


def ping_message() -> ServerSentEvent:
    """具名的 ping 事件（04 第 10 节），数据为空对象（PingEvent）。"""
    return ServerSentEvent(event="ping", data="{}")


def _event(ctx: AppContext, name: str, data: Any) -> dict[str, Any]:
    return {"event": name, "id": str(ctx.bus.next_event_id()), "data": json.dumps(data, ensure_ascii=False)}


async def _next(sub: Subscriber, timeout: float) -> BusEvent | None:
    try:
        return await asyncio.wait_for(sub.queue.get(), timeout=max(0.001, timeout))
    except TimeoutError:
        return None


def _drain(sub: Subscriber) -> list[BusEvent]:
    events: list[BusEvent] = []
    while not sub.queue.empty():
        events.append(sub.queue.get_nowait())
    return events


async def global_stream(ctx: AppContext) -> AsyncIterator[dict[str, Any]]:
    sub = ctx.bus.subscribe(None)
    last_sent: dict[int, float] = {}
    pending: dict[int, bool] = {}   # job_id → 是否有状态变化
    try:
        while True:
            now = time.monotonic()
            due = [last_sent.get(j, 0.0) + JOB_INTERVAL for j, changed in pending.items() if not changed]
            wait_until = min(due) if due else now + IDLE_WAIT
            if any(pending.values()):
                wait_until = now
            event = await _next(sub, wait_until - now)
            if sub.overflowed:
                return
            events = ([event] if event else []) + _drain(sub)
            for ev in events:
                if ev.kind == JOB_CREATED:
                    summary = await job_service.get_summary(ctx, ev.job_id)
                    if summary is not None:
                        yield _event(ctx, "job.created", summary.model_dump())
                        last_sent[ev.job_id] = time.monotonic()
                    pending.pop(ev.job_id, None)
                elif ev.kind == JOB_DELETED:
                    pending.pop(ev.job_id, None)
                    last_sent.pop(ev.job_id, None)
                    yield _event(ctx, "job.deleted", {"job_id": ev.job_id})
                elif ev.kind == JOB_CHANGED:
                    pending[ev.job_id] = pending.get(ev.job_id, False) or ev.status_changed
            now = time.monotonic()
            for job_id, changed in list(pending.items()):
                if changed or now - last_sent.get(job_id, 0.0) >= JOB_INTERVAL:
                    pending.pop(job_id, None)
                    summary = await job_service.get_summary(ctx, job_id)
                    if summary is not None:
                        yield _event(ctx, "job.updated", summary.model_dump())
                        last_sent[job_id] = time.monotonic()
    finally:
        ctx.bus.unsubscribe(sub)


async def job_stream(ctx: AppContext, job_id: int) -> AsyncIterator[dict[str, Any]]:
    sub = ctx.bus.subscribe(job_id)
    job_dirty = False
    status_changed = False
    item_ids: dict[int, None] = {}
    tracks_dirty = False
    last_job = 0.0
    last_tracks: list[dict[str, Any]] | None = None
    try:
        while True:
            now = time.monotonic()
            wait_until = now + IDLE_WAIT
            if job_dirty:
                wait_until = min(wait_until, last_job + JOB_INTERVAL)
            first = await _next(sub, wait_until - now)
            if sub.overflowed:
                return
            events: list[BusEvent] = [first] if first else []
            if first is not None:
                # 250 毫秒窗口：把窗口内的变化合并成一次推送
                window_end = time.monotonic() + WINDOW
                while True:
                    remaining = window_end - time.monotonic()
                    if remaining <= 0:
                        break
                    more = await _next(sub, remaining)
                    if more is None:
                        break
                    events.append(more)
                    events.extend(_drain(sub))
                if sub.overflowed:
                    return
            for ev in events:
                if ev.kind == JOB_DELETED:
                    return
                if ev.kind in (JOB_CHANGED, JOB_CREATED):
                    job_dirty = True
                    status_changed = status_changed or ev.status_changed
                elif ev.kind == ITEMS_CHANGED:
                    for item_id in ev.item_ids:
                        item_ids.pop(item_id, None)
                        item_ids[item_id] = None
                    job_dirty = True
                elif ev.kind == TRACKS_CHANGED:
                    tracks_dirty = True
            now = time.monotonic()
            if job_dirty and (status_changed or now - last_job >= JOB_INTERVAL):
                live = await job_service.get_live(ctx, job_id)
                job_dirty = False
                status_changed = False
                last_job = time.monotonic()
                if live is None:
                    return
                yield _event(ctx, "job.updated", live.model_dump())
            if item_ids:
                ids = list(item_ids)
                item_ids.clear()
                summaries = await job_service.summaries_by_ids(ctx, job_id, ids)
                for start in range(0, len(summaries), ITEMS_PER_EVENT):
                    chunk = summaries[start : start + ITEMS_PER_EVENT]
                    yield _event(
                        ctx, "items.updated", {"job_id": job_id, "items": [s.model_dump() for s in chunk]}
                    )
            if tracks_dirty:
                tracks_dirty = False
                tracks = ctx.manager.tracks(job_id)
                if tracks != last_tracks:
                    last_tracks = tracks
                    yield _event(ctx, "tracks.updated", {"job_id": job_id, "items": tracks})
    finally:
        ctx.bus.unsubscribe(sub)


@router.get(
    "/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "SSE 事件流（数据结构见 JobSummary、JobLive、ItemsUpdatedEvent、TracksUpdatedEvent、"
                "JobDeletedEvent、PingEvent）"
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def stream_events(
    job_id: int | None = Query(None, description="不传为全局流；传了为单个任务的事件流"),
    ctx: AppContext = Depends(get_ctx),
) -> EventSourceResponse:
    if job_id is not None:
        async with ctx.db.session() as session:
            if await jobs_repo.get(session, job_id) is None:
                raise not_found("任务不存在")
        stream = job_stream(ctx, job_id)
    else:
        stream = global_stream(ctx)
    return EventSourceResponse(
        stream,
        ping=PING_INTERVAL,
        ping_message_factory=ping_message,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
