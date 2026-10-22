"""本地化的接口文档 /docs（04 第 12 节）。

FastAPI 默认的 Swagger UI 从 CDN 加载，离线或国内网络下常常白屏：构造应用时关掉它（docs_url=None），
这里自己注册 /docs，脚本和样式由后端从 app/vendor/swagger-ui/ 以 /docs-assets/ 路径提供。
Authorize 填过一次 X-WenShu-Client 后刷新页面不用重填（persistAuthorization）。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

ASSET_MEDIA_TYPES = {
    "swagger-ui-bundle.js": "text/javascript; charset=utf-8",
    "swagger-ui.css": "text/css; charset=utf-8",
}

router = APIRouter(include_in_schema=False)


@router.get("/docs")
async def swagger_ui(request: Request) -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{request.app.title} - 接口文档",
        swagger_js_url="/docs-assets/swagger-ui-bundle.js",
        swagger_css_url="/docs-assets/swagger-ui.css",
        swagger_favicon_url="/favicon.svg",
        # validatorUrl=None：不去请求 validator.swagger.io，保证完全不联网
        swagger_ui_parameters={"persistAuthorization": True, "validatorUrl": None},
    )


@router.get("/docs-assets/{name}")
async def docs_asset(name: str, request: Request) -> Response:
    media_type = ASSET_MEDIA_TYPES.get(name)
    path = request.app.state.cfg.swagger_dir / name
    if media_type is None or not path.is_file():
        return PlainTextResponse("资源不存在", status_code=404)
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})
