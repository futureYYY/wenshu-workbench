"""前端静态文件与 SPA 回退（04 第 12 节）。

- /assets/* 返回带哈希的资源，长缓存；
- 其他不以 /api、/mock、/docs、/docs-assets、/openapi.json 开头的 GET：static 目录下有这个文件（如 /favicon.svg）
  就直接返回，没有才返回 index.html（no-cache），交给前端路由；解析路径时防止 .. 跳出 static 目录；
- 静态目录不存在时返回 200 的纯文字说明，接口不受影响。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from app.api.errors import error_body

NOT_BUILT_TEXT = "前端尚未构建。运行 scripts\\build-web.bat 构建，或用 scripts\\dev.bat 开发。"
RESERVED_PREFIXES = ("api", "mock", "docs", "docs-assets", "openapi.json")

# Windows 上 mimetypes 会读注册表，.js 可能被映射成 text/plain，浏览器会拒绝加载模块脚本（白屏）；
# 常见的前端资源一律显式指定类型
MEDIA_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}


def _media_type(path: Path) -> str | None:
    return MEDIA_TYPES.get(path.suffix.lower())


def _safe_child(root: Path, relative: str) -> Path | None:
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate if candidate.is_file() else None


def build_static_router(static_dir: Path) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    @router.get("/assets/{asset_path:path}")
    async def serve_asset(asset_path: str) -> Response:
        if not (static_dir / "index.html").is_file():
            return PlainTextResponse(NOT_BUILT_TEXT, status_code=404)
        target = _safe_child(static_dir / "assets", asset_path)
        if target is None:
            return PlainTextResponse("资源不存在", status_code=404)
        return FileResponse(
            target, media_type=_media_type(target), headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )

    @router.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> Response:
        first = full_path.split("/", 1)[0]
        if first in RESERVED_PREFIXES:
            return JSONResponse(status_code=404, content=error_body("NOT_FOUND", "接口不存在"))
        index = static_dir / "index.html"
        if not index.is_file():
            return PlainTextResponse(NOT_BUILT_TEXT, status_code=200)
        if full_path:
            direct = _safe_child(static_dir, full_path)
            if direct is not None and direct.name != "index.html":
                return FileResponse(direct, media_type=_media_type(direct), headers={"Cache-Control": "no-cache"})
        return FileResponse(index, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    return router
