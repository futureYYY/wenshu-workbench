"""AppError 与统一错误处理（04 第 1、2 节）。

所有错误都返回 {"error": {"code", "message", "detail"}}，message 是可以直接展示的中文。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail or {}


# ---- 常用错误的构造函数 ----


def bad_request(message: str, **detail: Any) -> AppError:
    return AppError(400, "BAD_REQUEST", message, detail)


def not_found(message: str = "资源不存在", **detail: Any) -> AppError:
    return AppError(404, "NOT_FOUND", message, detail)


def conflict(code: str, message: str, **detail: Any) -> AppError:
    return AppError(409, code, message, detail)


def unprocessable(code: str, message: str, **detail: Any) -> AppError:
    return AppError(422, code, message, detail)


def field_error(path: str, message: str) -> AppError:
    """单个字段的校验错误，结构与 FastAPI 校验错误转换后的一致。"""
    label = _label_for(path)
    return AppError(
        422,
        "VALIDATION_ERROR",
        f"填写的内容有误：{label}{message}",
        {"fields": [{"path": path, "message": message}]},
    )


def error_body(code: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


# OpenAPI 里给每个 /api 接口声明的错误响应，前端据此得到错误体的类型
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "参数错误"},
    403: {"model": ErrorResponse, "description": "非本机访问或缺少 X-WenShu-Client 请求头"},
    404: {"model": ErrorResponse, "description": "资源不存在"},
    409: {"model": ErrorResponse, "description": "当前状态不允许该操作"},
    422: {"model": ErrorResponse, "description": "校验失败"},
    500: {"model": ErrorResponse, "description": "内部错误"},
}

# ---- 校验错误转中文 ----

_FIELD_LABELS = {
    "name": "名称",
    "base_url": "接口地址",
    "api_key": "API Key",
    "model": "模型名",
    "temperature": "温度",
    "max_output_tokens": "最大输出",
    "max_tokens_param": "最大输出参数名",
    "context_window": "上下文长度",
    "timeout_s": "超时",
    "concurrency_cap": "并发上限",
    "proxy_url": "代理",
    "extra_headers": "自定义请求头",
    "extra_body": "额外请求体",
    "notes": "备注",
    "concurrency": "并发",
    "max_retries": "失败重试次数",
    "limit": "处理条数",
    "start_row": "起始行",
    "header_row": "表头行",
    "text_columns": "文本列",
    "task_type": "任务类型",
    "file_id": "文件",
    "prompt_id": "提示词",
    "model_id": "模型",
    "system_prompt": "系统提示词",
    "user_template": "用户消息模板",
    "chunk_template": "分段模板",
    "merge_template": "合并模板",
    "field_map": "输出字段映射",
    "description": "说明",
    "note": "版本说明",
    "text": "文本",
    "default_limit": "默认处理条数",
    "default_max_retries": "默认重试次数",
    "preferred_port": "端口",
    "manual_label": "人工修正的意图",
    "manual_summary": "人工修改的摘要",
}

# 联合类型校验失败时，错误位置里会带成员类名（如 body.PromptInput.name）：
# 顶层的 PromptInput | PromptCopy 按请求体里有没有 copy_from_id 只保留一种；显示路径时去掉类名
_UNION_MEMBERS = {"PromptInput", "PromptCopy", "ClassifyFieldMap", "SummarizeFieldMap", "SampleText", "SampleRow"}


def _label_for(path: str) -> str:
    last = path.split(".")[-1] if path else ""
    label = _FIELD_LABELS.get(last)
    return f"{label}（{path}）" if label and label != path else (path or "请求")


def _message_for(err: dict[str, Any]) -> str:
    etype = str(err.get("type", ""))
    ctx = err.get("ctx") or {}
    msg = str(err.get("msg", ""))
    if etype == "missing":
        return "必填"
    if etype in ("int_parsing", "int_type", "int_from_float"):
        return "必须是整数"
    if etype in ("float_parsing", "float_type"):
        return "必须是数字"
    if etype in ("bool_parsing", "bool_type"):
        return "必须是 true 或 false"
    if etype in ("string_type",):
        return "必须是文本"
    if etype == "literal_error":
        expected = str(ctx.get("expected", ""))
        return f"取值必须是 {expected}" if expected else "取值不正确"
    if etype in ("list_type", "tuple_type"):
        return "必须是数组"
    if etype in ("dict_type", "model_type", "model_attributes_type", "dataclass_type"):
        return "格式不正确"
    if etype == "too_short":
        return f"至少需要 {ctx.get('min_length', 1)} 项"
    if etype == "too_long":
        return f"最多 {ctx.get('max_length')} 项"
    if etype == "greater_than_equal":
        return f"必须大于或等于 {ctx.get('ge')}"
    if etype == "less_than_equal":
        return f"必须小于或等于 {ctx.get('le')}"
    if etype == "greater_than":
        return f"必须大于 {ctx.get('gt')}"
    if etype == "less_than":
        return f"必须小于 {ctx.get('lt')}"
    if etype == "json_invalid":
        return "不是有效的 JSON"
    if etype in ("union_tag_invalid", "union_tag_not_found"):
        return "kind 取值不正确"
    if etype == "value_error":
        return msg.removeprefix("Value error, ")
    if etype in ("string_too_short",):
        return "不能为空"
    if etype in ("string_too_long",):
        return f"不能超过 {ctx.get('max_length')} 个字"
    # PydanticCustomError 的说明本身就是中文
    if msg and not msg.isascii():
        return msg
    return "格式不正确"


def _pick_union_branch(errors: list[dict[str, Any]], body: Any) -> list[dict[str, Any]]:
    def branch(err: dict[str, Any]) -> str | None:
        loc = err.get("loc", ())
        return str(loc[1]) if len(loc) > 1 and str(loc[1]) in ("PromptInput", "PromptCopy") else None

    if not any(branch(e) for e in errors):
        return errors
    drop = "PromptInput" if isinstance(body, dict) and "copy_from_id" in body else "PromptCopy"
    kept = [e for e in errors if branch(e) != drop]
    return kept or errors


def validation_fields(errors: list[dict[str, Any]], body: Any = None) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for err in _pick_union_branch(list(errors), body):
        loc = [str(p) for p in err.get("loc", ()) if str(p) not in _UNION_MEMBERS]
        if loc and loc[0] in ("body", "query", "path", "header", "cookie"):
            loc = loc[1:]
        fields.append({"path": ".".join(loc), "message": _message_for(err)})
    return fields


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message, exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = validation_fields(list(exc.errors()), getattr(exc, "body", None))
        if fields:
            first = fields[0]
            message = f"填写的内容有误：{_label_for(first['path'])}{first['message']}"
            if len(fields) > 1:
                message += f"，另有 {len(fields) - 1} 处"
        else:
            message = "填写的内容有误"
        return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", message, {"fields": fields}))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return JSONResponse(status_code=404, content=error_body("NOT_FOUND", "接口不存在"))
        if exc.status_code == 405:
            return JSONResponse(status_code=405, content=error_body("BAD_REQUEST", "不支持这个请求方法"))
        message = exc.detail if isinstance(exc.detail, str) and not exc.detail.isascii() else "请求有误"
        return JSONResponse(status_code=exc.status_code, content=error_body("BAD_REQUEST", message))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理的异常：%s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", "内部错误，详情见日志"))
