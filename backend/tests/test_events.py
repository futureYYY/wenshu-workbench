"""实时事件 SSE（04 第 10 节；08 第 4 节验收：curl -N /api/events?job_id= 能看到各类事件）。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .conftest import Api, LiveServer, unique_lines


class Listener(threading.Thread):
    def __init__(self, url: str, until: set[str], timeout: float = 30) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.until = until
        self.timeout = timeout
        self.events: list[tuple[str, Any]] = []
        self.ready = threading.Event()

    def run(self) -> None:
        deadline = time.monotonic() + self.timeout
        with httpx.Client(trust_env=False, timeout=self.timeout) as client, client.stream("GET", self.url) as resp:
            self.ready.set()
            name: str | None = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and name:
                    self.events.append((name, json.loads(line.split(":", 1)[1].strip())))
                    name = None
                if self.until <= {n for n, _ in self.events} or time.monotonic() > deadline:
                    return

    @property
    def names(self) -> set[str]:
        return {n for n, _ in self.events}


def test_job_stream(api: Api) -> None:
    model = api.mock_model("事件-单任务")
    job = api.create_job(api.paste(unique_lines("单任务事件", 20)), model_id=model["id"], concurrency=4, limit=None)
    listener = Listener(f"{api.server.base_url}/api/events?job_id={job['id']}", {"job.updated", "items.updated", "tracks.updated"})
    listener.start()
    listener.join(40)
    assert {"job.updated", "items.updated", "tracks.updated"} <= listener.names
    live = next(d for n, d in listener.events if n == "job.updated")
    assert live["id"] == job["id"] and "categories" in live and "usage" in live
    items = next(d for n, d in listener.events if n == "items.updated")
    assert items["job_id"] == job["id"] and items["items"] and "input_preview" in items["items"][0]
    tracks = next(d for n, d in listener.events if n == "tracks.updated")
    assert tracks["job_id"] == job["id"] and len(tracks["items"]) <= 4
    api.wait_job(job["id"])


def test_global_stream(api: Api, fast_model: dict[str, Any]) -> None:
    listener = Listener(f"{api.server.base_url}/api/events", {"job.created", "job.updated"})
    listener.start()
    assert listener.ready.wait(10)
    time.sleep(0.3)
    job = api.create_job(api.paste(unique_lines("全局事件", 3)), model_id=fast_model["id"])
    listener.join(30)
    created = [d for n, d in listener.events if n == "job.created"]
    assert any(d["id"] == job["id"] for d in created)
    assert "progress" in created[0] and "categories" not in created[0]  # 全局流是 JobSummary
    api.wait_job(job["id"])


def test_unknown_job_stream_404(api: Api) -> None:
    api.error(api.get("/api/events", params={"job_id": 999999}), 404, "NOT_FOUND")


def test_ping_is_named_event() -> None:
    """04 第 10 节：ping 必须是具名事件（event: ping），sse-starlette 默认的注释行前端收不到。"""
    from app.api.events import PING_INTERVAL, ping_message

    encoded = ping_message().encode()
    text = encoded.decode("utf-8") if isinstance(encoded, bytes) else str(encoded)
    assert "event: ping" in text and "data: {}" in text
    assert PING_INTERVAL == 15


def test_stop_ends_open_streams(tmp_path: Path) -> None:
    """02 第 5.7 节：先设 AppStatus.should_exit 结束事件流，再停 uvicorn。界面开着时服务也能很快退出，
    不用等 timeout_graceful_shutdown（5 秒）兜底。"""
    live = LiveServer(tmp_path / "data").start()
    listener = Listener(f"{live.base_url}/api/events", {"never"}, timeout=60)
    listener.start()
    assert listener.ready.wait(10)
    time.sleep(0.3)
    started = time.monotonic()
    live.stop()
    assert time.monotonic() - started < 4, "事件流没有在停服务之前结束"
    listener.join(5)
    assert not listener.is_alive()
