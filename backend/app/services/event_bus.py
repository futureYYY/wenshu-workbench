"""进程内发布订阅，供 SSE 使用（02 第 7 节）。

总线上传的是轻量的“变化通知”（哪个任务、哪些条目变了），SSE 连接在 250 毫秒窗口里合并后，
再从数据库和任务引擎读取最新数据推给前端。每个订阅者一个有界队列（容量 2,000），
满了说明客户端太慢：标记溢出，SSE 连接随即断开，客户端自动重连并重新拉取。
"""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass

QUEUE_SIZE = 2000

JOB_CREATED = "job.created"
JOB_CHANGED = "job.changed"
JOB_DELETED = "job.deleted"
ITEMS_CHANGED = "items.changed"
TRACKS_CHANGED = "tracks.changed"

GLOBAL_KINDS = frozenset({JOB_CREATED, JOB_CHANGED, JOB_DELETED})


@dataclass(frozen=True)
class BusEvent:
    kind: str
    job_id: int
    status_changed: bool = False
    item_ids: tuple[int, ...] = ()


class Subscriber:
    def __init__(self, job_id: int | None) -> None:
        self.job_id = job_id
        self.queue: asyncio.Queue[BusEvent] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.overflowed = False


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()
        self._ids = itertools.count(1)
        # 只在事件循环线程里改、托盘线程只读的整数（首次关闭提示用）
        self.global_subscriber_count = 0

    def next_event_id(self) -> int:
        return next(self._ids)

    def subscribe(self, job_id: int | None) -> Subscriber:
        sub = Subscriber(job_id)
        self._subscribers.add(sub)
        if job_id is None:
            self.global_subscriber_count += 1
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        if sub in self._subscribers:
            self._subscribers.discard(sub)
            if sub.job_id is None:
                self.global_subscriber_count = max(0, self.global_subscriber_count - 1)

    def has_job_subscribers(self, job_id: int) -> bool:
        return any(s.job_id == job_id for s in self._subscribers)

    def publish(self, event: BusEvent) -> None:
        for sub in list(self._subscribers):
            if sub.job_id is None:
                if event.kind not in GLOBAL_KINDS:
                    continue
            elif sub.job_id != event.job_id:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.overflowed = True

    def job_created(self, job_id: int) -> None:
        self.publish(BusEvent(JOB_CREATED, job_id, status_changed=True))

    def job_changed(self, job_id: int, *, status_changed: bool = False) -> None:
        self.publish(BusEvent(JOB_CHANGED, job_id, status_changed=status_changed))

    def job_deleted(self, job_id: int) -> None:
        self.publish(BusEvent(JOB_DELETED, job_id, status_changed=True))

    def items_changed(self, job_id: int, item_ids: tuple[int, ...] | list[int]) -> None:
        if item_ids:
            self.publish(BusEvent(ITEMS_CHANGED, job_id, item_ids=tuple(item_ids)))

    def tracks_changed(self, job_id: int) -> None:
        self.publish(BusEvent(TRACKS_CHANGED, job_id))
