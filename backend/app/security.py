"""请求检查中间件（02 第 10 节、04 第 1 节）。

- Host 必须是 127.0.0.1:{端口} 或 localhost:{端口}（防 DNS 重绑定），端口取服务实际监听的端口；
- 除 GET、HEAD、OPTIONS 外的 /api 请求必须带 X-WenShu-Client: 1；
- /mock 不检查；
- 上传接口在读请求体之前按 Content-Length 拒绝超过 50 MB 的文件（04 第 7 节）；
- 4xx、5xx 响应记一行日志（打包后关闭了 Uvicorn 访问日志）。

用纯 ASGI 中间件实现，不影响 SSE 等流式响应。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from app.config import MAX_UPLOAD_BYTES

logger = logging.getLogger("app.access")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}   # OPTIONS：CORS 预检不带自定义请求头，不检查它
CLIENT_HEADER = "X-WenShu-Client"
# multipart 的边界和字段名会让请求体比文件本身大一点，留 1 MB 余量
UPLOAD_OVERHEAD = 1024 * 1024


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _error_payload(code: str, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message, "detail": {}}}, ensure_ascii=False).encode("utf-8")


async def _send_json(send: Send, status: int, code: str, message: str) -> None:
    body = _error_payload(code, message)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, port_holder: Any) -> None:
        self.app = app
        # port_holder.port：服务实际监听的端口，演示模型的地址也用它
        self.port_holder = port_holder

    def _allowed_hosts(self, scope: Scope) -> set[str]:
        server = scope.get("server")
        port = server[1] if server and len(server) > 1 and server[1] else self.port_holder.port
        if port != self.port_holder.port:
            self.port_holder.port = int(port)
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET").upper()

        if path.startswith("/mock"):
            await self.app(scope, receive, send)
            return

        host = (_header(scope, b"host") or "").strip().lower()
        if host not in self._allowed_hosts(scope):
            logger.warning("拒绝非本机地址的请求：Host=%s %s %s", host, method, path)
            await _send_json(send, 403, "FORBIDDEN", "只接受本机地址的访问")
            return

        if path.startswith("/api") and method not in SAFE_METHODS:
            if _header(scope, CLIENT_HEADER.lower().encode("ascii")) != "1":
                await _send_json(send, 403, "FORBIDDEN", "缺少请求头 X-WenShu-Client")
                return
            if path.rstrip("/") == "/api/files" and method == "POST":
                length = _header(scope, b"content-length")
                if length and length.isdigit() and int(length) > MAX_UPLOAD_BYTES + UPLOAD_OVERHEAD:
                    await _send_json(send, 413, "FILE_TOO_LARGE", "文件超过 50 MB，请拆分后再上传")
                    return

        status_holder: dict[str, int] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
            await send(message)

        await self.app(scope, receive, send_wrapper)
        status = status_holder.get("status", 0)
        if status >= 400 and path.startswith(("/api", "/mock")):
            logger.info("%s %s -> %d", method, path, status)
