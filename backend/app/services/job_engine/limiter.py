"""容量可在运行中调整的并发闸门（02 第 5.2 节）。任务级和模型级各用一个。"""

from __future__ import annotations

import asyncio
from collections import deque


class ResizableLimiter:
    """容量可在运行中调整的信号量。调大立即唤醒等待者；调小不打断进行中的，只限制之后的获取。"""

    def __init__(self, capacity: int) -> None:
        self._capacity = max(1, int(capacity))
        self._in_use = 0
        self._waiters: deque[asyncio.Future[None]] = deque()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def in_use(self) -> int:
        return self._in_use

    async def acquire(self) -> None:
        if self._in_use < self._capacity and not self._waiters:
            self._in_use += 1
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.append(future)
        try:
            await future
        except asyncio.CancelledError:
            if future.done() and not future.cancelled():
                # 名额已经分给了我们，但调用方被取消：归还名额
                self._in_use -= 1
                self._wake()
            else:
                try:
                    self._waiters.remove(future)
                except ValueError:
                    pass
            raise

    def release(self) -> None:
        if self._in_use > 0:
            self._in_use -= 1
        self._wake()

    def resize(self, capacity: int) -> None:
        self._capacity = max(1, int(capacity))
        self._wake()

    def _wake(self) -> None:
        while self._waiters and self._in_use < self._capacity:
            future = self._waiters.popleft()
            if future.done():
                continue
            self._in_use += 1
            future.set_result(None)


class ModelLimiters:
    """按模型 id 管理模型级闸门，容量为该模型的 concurrency_cap；同一模型被多个任务共用时共享。"""

    def __init__(self) -> None:
        self._limiters: dict[int, ResizableLimiter] = {}

    def get(self, model_id: int, capacity: int) -> ResizableLimiter:
        limiter = self._limiters.get(model_id)
        if limiter is None:
            limiter = ResizableLimiter(capacity)
            self._limiters[model_id] = limiter
        elif limiter.capacity != capacity:
            limiter.resize(capacity)
        return limiter

    def resize(self, model_id: int, capacity: int) -> None:
        limiter = self._limiters.get(model_id)
        if limiter is not None:
            limiter.resize(capacity)
