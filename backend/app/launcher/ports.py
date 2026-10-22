"""端口：先自己绑定 socket，再把它交给 Uvicorn（07 第 5.1 节第 3 步）。

这样“检查是否空闲”和“真正绑定”是同一个动作，中间不会被其他程序抢占。
"""

from __future__ import annotations

import logging
import socket
import sys

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"


def _new_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        # 绑定前设独占模式（07 第 5.1 节第 3 步）。不设的话，之后启动的开发用 uvicorn（开了 SO_REUSEADDR）
        # 还能绑定同一个端口，请求会随机落到两个进程上。常量只在 Windows 上存在
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            sock.setsockopt(socket.SOL_SOCKET, exclusive, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


def bind_socket(preferred: int) -> socket.socket:
    """优先绑定 127.0.0.1:preferred；被占用时改绑端口 0，由系统分配空闲端口。

    只绑定不监听：Uvicorn（asyncio.create_server）接手后会调用 listen()。
    """
    candidates = [preferred, 0] if preferred else [0]
    last_error: OSError | None = None
    for port in candidates:
        sock = _new_socket()
        try:
            sock.bind((HOST, port))
        except OSError as exc:
            sock.close()
            last_error = exc
            if port:
                logger.info("端口 %s 已被占用（%s），改用系统分配的空闲端口", port, exc)
            continue
        sock.set_inheritable(False)
        return sock
    raise OSError(f"无法在 {HOST} 上绑定端口：{last_error}")


def socket_port(sock: socket.socket) -> int:
    return int(sock.getsockname()[1])
