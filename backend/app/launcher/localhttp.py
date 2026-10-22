"""调用本机后端接口的小工具，启动器和自检共用。

只用标准库；不走系统代理（本机装了代理软件时，127.0.0.1 也可能被转发出去）；
非 GET 请求自动带 X-WenShu-Client: 1（02 第 10 节）。
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

HOST = "127.0.0.1"

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class HttpError(Exception):
    """后端返回了 4xx、5xx。"""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}：{body[:300]}")
        self.status = status
        self.body = body


# 调用方用它一次捕获所有“连不上、超时、返回异常”的情况
ERRORS: tuple[type[BaseException], ...] = (OSError, ValueError, http.client.HTTPException, HttpError)


def url(port: int, path: str) -> str:
    return f"http://{HOST}:{port}{path}"


def _build(port: int, path: str, method: str, body: Any) -> urllib.request.Request:
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    elif method != "GET":
        data = b""  # 让 urllib 带上 Content-Length: 0
    req = urllib.request.Request(url(port, path), data=data, method=method)
    if method != "GET":
        req.add_header("X-WenShu-Client", "1")
    if body is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    return req


def request(port: int, path: str, *, method: str = "GET", body: Any = None, timeout: float = 10.0) -> bytes:
    req = _build(port, path, method, body)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        payload = exc.read() if exc.fp is not None else b""
        raise HttpError(exc.code, payload.decode("utf-8", "replace")) from exc


def get_text(port: int, path: str, *, timeout: float = 10.0) -> str:
    return request(port, path, timeout=timeout).decode("utf-8", "replace")


def get_json(port: int, path: str, *, timeout: float = 10.0) -> Any:
    return json.loads(request(port, path, timeout=timeout).decode("utf-8"))


def post_json(port: int, path: str, body: Any = None, *, timeout: float = 30.0) -> Any:
    raw = request(port, path, method="POST", body=body, timeout=timeout)
    return json.loads(raw.decode("utf-8")) if raw else None


def health_ok(port: int, *, timeout: float = 2.0) -> bool:
    try:
        data = get_json(port, "/api/health", timeout=timeout)
    except ERRORS:
        return False
    return isinstance(data, dict) and data.get("status") == "ok"


def post_sse(port: int, path: str, body: Any, *, timeout: float = 60.0) -> Iterator[tuple[str, str]]:
    """POST 一个返回 text/event-stream 的接口，逐个产出 (事件名, data 文本)。"""
    req = _build(port, path, "POST", body)
    req.add_header("Accept", "text/event-stream")
    try:
        resp = _OPENER.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        payload = exc.read() if exc.fp is not None else b""
        raise HttpError(exc.code, payload.decode("utf-8", "replace")) from exc
    with resp:
        event = "message"
        data_lines: list[str] = []
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                if data_lines:
                    yield event, "\n".join(data_lines)
                event, data_lines = "message", []
                continue
            if line.startswith(":"):
                continue  # 注释行（心跳）
            field, _, value = line.partition(":")
            value = value.removeprefix(" ")
            if field == "event":
                event = value
            elif field == "data":
                data_lines.append(value)
        if data_lines:
            yield event, "\n".join(data_lines)
