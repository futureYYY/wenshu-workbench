"""进度与轨道（02 第 5.6 节、03 第 7 节）：进行中集合、最近 30 次完成的时间、速度。"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from app.utils import now_iso

RATE_WINDOW = 30
RATE_MIN_SAMPLES = 5


@dataclass
class TrackState:
    item_id: int
    seq: int
    row_number: int
    input_preview: str
    started_at: str
    attempt: int = 1
    phase: str = "request"
    phase_detail: str = ""
    retry_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "seq": self.seq,
            "row_number": self.row_number,
            "input_preview": self.input_preview,
            "started_at": self.started_at,
            "attempt": self.attempt,
            "phase": self.phase,
            "phase_detail": self.phase_detail,
            "retry_at": self.retry_at,
        }


def preview_text(text: str, limit: int) -> str:
    return text.replace("\r", " ").replace("\n", " ")[:limit]


class ProgressTracker:
    """每个任务一个，事件循环线程独占。"""

    def __init__(self) -> None:
        self.tracks: dict[int, TrackState] = {}
        self._completions: deque[float] = deque(maxlen=RATE_WINDOW)
        self.version = 0   # 轨道内容每次变化 +1，SSE 据此判断要不要发 tracks.updated

    @property
    def running(self) -> int:
        return len(self.tracks)

    def start(self, item_id: int, seq: int, row_number: int, text: str, attempt: int) -> None:
        self.tracks[item_id] = TrackState(
            item_id=item_id,
            seq=seq,
            row_number=row_number,
            input_preview=preview_text(text, 60),
            started_at=now_iso(),
            attempt=attempt,
        )
        self.version += 1

    def update(self, item_id: int, **fields: Any) -> None:
        track = self.tracks.get(item_id)
        if track is None:
            return
        for key, value in fields.items():
            setattr(track, key, value)
        self.version += 1

    def finish(self, item_id: int, *, completed: bool) -> None:
        if self.tracks.pop(item_id, None) is not None:
            self.version += 1
        if completed:
            self._completions.append(time.monotonic())

    def rate_per_min(self) -> float | None:
        """最近 30 条完成（成功或失败）的时间跨度计算；完成不足 5 条时为 null。"""
        if len(self._completions) < RATE_MIN_SAMPLES:
            return None
        span = self._completions[-1] - self._completions[0]
        if span <= 0:
            return None
        return round((len(self._completions) - 1) / span * 60, 1)

    def snapshot(self) -> list[dict[str, Any]]:
        return [t.as_dict() for t in sorted(self.tracks.values(), key=lambda t: t.started_at)]
