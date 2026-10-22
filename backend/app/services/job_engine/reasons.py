"""暂停原因码与对应文案（03 第 6.1 节）。

界面按 status_reason_code 决定提示和操作（06 第 6.3、6.4 节），status_reason 只给人看，不要拿它做判断。
"""

from __future__ import annotations

USER_PAUSE = "user_pause"
SHUTDOWN = "shutdown"
AUTH_FAILED = "auth_failed"
MODEL_NOT_FOUND = "model_not_found"
CIRCUIT_BREAKER = "circuit_breaker"
WRITE_FAILED = "write_failed"

REASON_CODES = (USER_PAUSE, SHUTDOWN, AUTH_FAILED, MODEL_NOT_FOUND, CIRCUIT_BREAKER, WRITE_FAILED)

USER_PAUSE_TEXT = "已手动暂停"
SHUTDOWN_TEXT = "程序退出时任务未完成，可以继续"
WRITE_FAILED_TEXT = "保存结果失败，请查看日志"
CIRCUIT_THRESHOLD = 10


def auth_failed_text(status_code: int | None) -> str:
    return f"模型密钥无效或无权限（HTTP {status_code or 401}）"


def model_not_found_text(model: str) -> str:
    return f"模型“{model}”不存在，或接口地址不对（HTTP 404）"


def circuit_breaker_text(last_error: str | None) -> str:
    return f"连续 {CIRCUIT_THRESHOLD} 条请求失败，最后一次：{last_error or '未知错误'}"
