"""接口：统一错误结构、中文校验信息、各个 409 场景、设置、模型、提示词（04；08 第 10.1 节“接口”）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app import __version__
from app.config import PLACEHOLDER_BASE_URL
from app.services.llm_client import ChatResult, ModelSpec
from app.services.model_service import run_test

from .conftest import Api, LiveServer


def test_health(api: Api) -> None:
    assert api.ok(api.get("/api/health")) == {"status": "ok", "version": __version__}


def test_system_info(api: Api) -> None:
    info = api.ok(api.get("/api/system/info"))
    assert info["version"] == __version__
    assert info["port"] == api.server.port
    assert info["run_mode"] == "dev" and info["dev_mode"] is True   # 测试服务按 02 第 11.1 节设 WENSHU_DEV=1
    assert Path(info["data_dir"]) == api.server.data_dir.resolve()


def test_non_get_requires_client_header(api: Api) -> None:
    with httpx.Client(base_url=api.server.base_url, trust_env=False) as bare:
        api.error(bare.patch("/api/settings", json={"theme": "dark"}), 403, "FORBIDDEN")
        assert bare.get("/api/settings").status_code == 200


def test_options_not_checked(api: Api) -> None:
    """CORS 预检是不带自定义请求头的 OPTIONS，不检查它（没有放行的来源时由路由返回 405，而不是 403）。"""
    with httpx.Client(base_url=api.server.base_url, trust_env=False) as bare:
        resp = bare.options("/api/settings")
    assert resp.status_code != 403


def test_cors_preflight_when_origins_configured(tmp_path: Path) -> None:
    """设置 WENSHU_CORS_ORIGINS 后跨来源预检通过：CORSMiddleware 在最外层先应答（02 第 10 节）。"""
    origin = "http://127.0.0.1:4173"
    live = LiveServer(tmp_path / "data", cors_origins=origin).start()
    try:
        with httpx.Client(base_url=live.base_url, trust_env=False) as bare:
            resp = bare.options(
                "/api/settings",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "x-wenshu-client,content-type",
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.headers["access-control-allow-origin"] == origin
            other = bare.options(
                "/api/settings",
                headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "PATCH"},
            )
            assert "access-control-allow-origin" not in other.headers
    finally:
        live.stop()


def test_foreign_host_rejected(api: Api) -> None:
    resp = api.get("/api/health", headers={"Host": "evil.example.com"})
    api.error(resp, 403, "FORBIDDEN")
    assert api.get("/api/health", headers={"Host": f"localhost:{api.server.port}"}).status_code == 200


def test_mock_not_checked(api: Api) -> None:
    with httpx.Client(base_url=api.server.base_url, trust_env=False) as bare:
        resp = bare.post(
            "/mock/v1/chat/completions",
            json={"model": "wenshu-demo", "messages": [{"role": "user", "content": "请只回复：OK"}]},
            headers={"Host": "anything.local", "X-Mock-Behavior": "fast"},
        )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "OK"


def test_unknown_api_path_is_json_404(api: Api) -> None:
    api.error(api.get("/api/no-such-thing"), 404, "NOT_FOUND")


def test_root_page(api: Api) -> None:
    resp = api.get("/")
    assert resp.status_code == 200
    static_index = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
    if static_index.exists():
        assert "text/html" in resp.headers["content-type"]
    else:
        assert "前端尚未构建" in resp.text


def test_validation_error_is_chinese(api: Api) -> None:
    file = api.paste("校验测试")
    body = api.job_body(file, model_id=api.demo_model_id(), concurrency=25)
    err = api.error(api.post("/api/jobs", body), 422, "VALIDATION_ERROR")
    assert {"path": "concurrency", "message": "必须在 1 到 20 之间"} in err["detail"]["fields"]
    assert "并发" in err["message"]
    missing = api.error(api.post("/api/models", {"name": "缺字段"}), 422, "VALIDATION_ERROR")
    assert {f["path"] for f in missing["detail"]["fields"]} >= {"base_url", "model"}


# ---- 设置 ----


def test_settings_defaults_and_patch(fresh_api: Api) -> None:
    settings = fresh_api.ok(fresh_api.get("/api/settings"))
    demo = fresh_api.demo_model_id()
    assert settings["default_concurrency"] == {"classify": 5, "summarize": 5}
    assert settings["default_limit"] == 100 and settings["default_max_retries"] == 2
    assert settings["default_dedupe"] is True and settings["theme"] == "system" and settings["open_mode"] == "app"
    assert settings["default_model_id"] == {"classify": demo, "summarize": demo}
    assert settings["limits"] == {"max_concurrency": 20, "max_rows_per_source": 100000, "max_upload_bytes": 52428800}

    patched = fresh_api.ok(fresh_api.patch("/api/settings", {"default_concurrency": {"classify": 8}}))
    assert patched["default_concurrency"] == {"classify": 8, "summarize": 5}
    patched = fresh_api.ok(fresh_api.patch("/api/settings", {"default_limit": None, "theme": "dark"}))
    assert patched["default_limit"] is None and patched["theme"] == "dark"
    patched = fresh_api.ok(fresh_api.patch("/api/settings", {"default_model_id": {"summarize": None}}))
    assert patched["default_model_id"] == {"classify": demo, "summarize": None}
    fresh_api.error(fresh_api.patch("/api/settings", {"theme": "pink"}), 422, "VALIDATION_ERROR")
    fresh_api.error(fresh_api.patch("/api/settings", {"default_model_id": {"classify": 99999}}), 422, "VALIDATION_ERROR")
    summarize_prompt = fresh_api.builtin_prompt("summarize")["id"]
    fresh_api.error(
        fresh_api.patch("/api/settings", {"default_prompt_id": {"classify": summarize_prompt}}), 422, "VALIDATION_ERROR"
    )


# ---- 模型 ----


def test_model_crud_and_conflicts(api: Api) -> None:
    created = api.mock_model("CRUD 模型", notes="备注")
    assert created["provider_kind"] == "openai_compatible"
    assert created["request_url"] == f"{api.server.base_url}/mock/v1/chat/completions"
    api.error(api.post("/api/models", {"name": "CRUD 模型", "base_url": "http://x", "model": "m"}), 409, "MODEL_NAME_TAKEN")

    pasted = api.ok(
        api.post(
            "/api/models",
            {"name": "带后缀的地址", "base_url": " https://api.example.org/v1/chat/completions/ ", "model": "m"},
        ),
        201,
    )
    assert pasted["base_url"] == "https://api.example.org/v1"
    api.error(api.post("/api/models", {"name": "坏地址", "base_url": "ftp://x", "model": "m"}), 422, "VALIDATION_ERROR")

    patched = api.ok(api.patch(f"/api/models/{created['id']}", {"temperature": 1.2, "concurrency_cap": 8}))
    assert patched["temperature"] == 1.2 and patched["concurrency_cap"] == 8
    assert api.delete(f"/api/models/{pasted['id']}").status_code == 204
    api.error(api.get(f"/api/models/{pasted['id']}"), 404, "NOT_FOUND")


def test_demo_model_protected(api: Api) -> None:
    demo = api.demo_model_id()
    api.error(api.delete(f"/api/models/{demo}"), 409, "DEMO_MODEL_PROTECTED")
    api.error(api.patch(f"/api/models/{demo}", {"base_url": "http://127.0.0.1:1/v1"}), 409, "DEMO_MODEL_PROTECTED")
    renamed = api.ok(api.patch(f"/api/models/{demo}", {"notes": "改备注", "context_window": 32768}))
    assert renamed["notes"] == "改备注" and renamed["request_url"] == "本机模拟"


def test_model_test_and_list_remote(api: Api) -> None:
    demo = api.demo_model_id()
    result = api.ok(api.post(f"/api/models/{demo}/test"))
    assert result["ok"] is True and result["message"].startswith("连接正常") and result["sample_output"] == "OK"
    detail = api.ok(api.get(f"/api/models/{demo}"))
    assert detail["last_test"]["ok"] is True

    draft = {"name": "草稿", "base_url": f"{api.server.base_url}/mock/v1", "model": "wenshu-demo"}
    assert api.ok(api.post("/api/models/test-draft", {"config": draft}))["ok"] is True
    assert api.ok(api.post("/api/models/list-remote", {"config": draft}))["models"] == ["wenshu-demo"]

    auth = api.ok(
        api.post("/api/models/test-draft", {"config": {**draft, "extra_headers": {"X-Mock-Behavior": "auth"}}})
    )
    assert auth["ok"] is False and auth["error_code"] == "AUTH_FAILED"
    assert auth["message"] == "密钥无效或无权限（HTTP 401）" and auth["status_code"] == 401

    missing = {**draft, "base_url": f"{api.server.base_url}/mock/no-such"}
    err = api.error(api.post("/api/models/list-remote", {"config": missing}), 502, "UPSTREAM_ERROR")
    assert err["message"] == "这个接口不支持获取模型列表，请手动填写模型名"


def test_test_connection_ignores_json_mode(api: Api) -> None:
    model = api.mock_model("JSON 模式测试", json_mode=True, extra_body={"response_format": {"type": "json_object"}})
    assert api.ok(api.post(f"/api/models/{model['id']}/test"))["ok"] is True


async def test_run_test_never_sends_response_format() -> None:
    """05 第 9 节：测试连接不发 response_format（DeepSeek 等要求提示词含 json，否则 400）。"""
    captured: dict[str, Any] = {}

    class FakeLLM:
        async def chat(self, spec: ModelSpec, messages: list[dict[str, str]], **kw: Any) -> ChatResult:
            captured.update(spec=spec, messages=messages, kw=kw)
            return ChatResult("OK", None, "stop", 5, 1, 12)

    spec = ModelSpec(
        id=1, name="x", provider_kind="openai_compatible", base_url="https://api.example.org/v1", api_key=None,
        model="m", json_mode=True, extra_body={"response_format": {"type": "json_object"}, "enable_thinking": False},
    )
    result = await run_test(FakeLLM(), spec)  # type: ignore[arg-type]
    assert result.ok and result.sample_output == "OK"
    assert captured["spec"].json_mode is False
    assert captured["spec"].extra_body == {"enable_thinking": False}
    assert captured["kw"]["json_output"] is False and captured["kw"]["max_tokens"] == 32
    assert captured["messages"] == [{"role": "user", "content": "请只回复：OK"}]


def test_first_real_model_becomes_default(fresh_api: Api) -> None:
    first = fresh_api.mock_model("第一个真实模型")
    assert sorted(first["default_for"]) == ["classify", "summarize"]
    settings = fresh_api.ok(fresh_api.get("/api/settings"))
    assert settings["default_model_id"] == {"classify": first["id"], "summarize": first["id"]}
    second = fresh_api.mock_model("第二个真实模型")
    assert second["default_for"] == []


def test_placeholder_model(fresh_api: Api) -> None:
    models = fresh_api.ok(fresh_api.get("/api/models", params={"include_demo": True}))["items"]
    placeholder = next(m for m in models if m["base_url"] == PLACEHOLDER_BASE_URL)
    assert placeholder["enabled"] is False and placeholder["has_api_key"] is False
    assert models[-1]["provider_kind"] == "demo"  # 演示模型排在最后
    filled = fresh_api.ok(
        fresh_api.patch(
            f"/api/models/{placeholder['id']}",
            {"base_url": f"{fresh_api.server.base_url}/mock/v1", "model": "wenshu-demo"},
        )
    )
    assert filled["enabled"] is True
    assert sorted(filled["default_for"]) == ["classify", "summarize"]


def test_local_models_file_import(tmp_path: Path) -> None:
    models_file = tmp_path / "models.local.json"
    secret = "sk-local-file-key-1234abcd"
    models_file.write_text(
        json.dumps({"name": "本机配置模型", "base_url": "https://api.example.org/v1", "api_key": secret, "model": "m-1"}),
        encoding="utf-8",
    )
    live = LiveServer(tmp_path / "data", models_file=models_file).start()
    try:
        client = Api(live)
        models = client.ok(client.get("/api/models", params={"include_demo": True}))["items"]
        imported = next(m for m in models if m["name"] == "本机配置模型")
        assert imported["has_api_key"] and imported["api_key_masked"] == "sk-…abcd"
        assert sorted(imported["default_for"]) == ["classify", "summarize"]
        assert not any(m["base_url"] == PLACEHOLDER_BASE_URL for m in models)  # 占位条目被配置替换
        assert secret.encode() not in (live.data_dir / "wenshu.db").read_bytes()
        client.client.close()
    finally:
        live.stop()


def test_model_in_use_cannot_be_deleted(api: Api) -> None:
    model = api.mock_model("占用中的模型", "auth")
    file = api.paste("占用测试 1\n占用测试 2")
    job = api.create_job(file, model_id=model["id"], concurrency=1)
    api.wait_job(job["id"], ("paused",))
    api.error(api.delete(f"/api/models/{model['id']}"), 409, "MODEL_IN_USE")
    api.error(api.delete(f"/api/files/{file['id']}"), 409, "FILE_IN_USE")
    assert api.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert api.delete(f"/api/models/{model['id']}").status_code == 204


# ---- 提示词 ----

CLASSIFY_DRAFT = {
    "task_type": "classify",
    "system_prompt": "从类别中选一个，输出 JSON：{\"intent\": \"类别\"}\n- 咨询：问问题\n- 投诉：表达不满",
    "user_template": "{{text}}",
    "output_mode": "json",
    "field_map": {"label": "intent", "confidence": None, "reason": None},
}


def test_prompt_list_order_and_variables(api: Api) -> None:
    items = api.ok(api.get("/api/prompts", params={"task_type": "classify"}))["items"]
    assert items[0]["is_default"] and items[0]["builtin_key"] == "classify.default"
    variables = api.ok(api.get("/api/prompts/variables", params={"task_type": "summarize"}))["items"]
    names = {v["name"] for v in variables}
    assert {"text", "text_numbered", "chunk_summaries", "col:"} <= names
    col = next(v for v in variables if v["name"] == "col:")
    assert col["insert"] == "{{col:}}"


def test_prompt_save_validation(api: Api) -> None:
    no_input = {**CLASSIFY_DRAFT, "name": "没有输入变量", "user_template": "只有 {{today}}"}
    api.error(api.post("/api/prompts", no_input), 422, "PROMPT_NO_INPUT_VARIABLE")
    summary = {
        "task_type": "summarize",
        "name": "缺分段模板",
        "system_prompt": "输出 JSON",
        "user_template": "{{text_numbered}}",
        "output_mode": "json",
        "field_map": {"summary": "summary", "key_points": "key_points"},
        "merge_template": "{{chunk_summaries}}",
    }
    api.error(api.post("/api/prompts", summary), 422, "PROMPT_TEMPLATE_MISSING")
    api.error(api.post("/api/prompts", {**summary, "chunk_template": "{{text}}", "merge_template": "无变量"}), 422,
              "PROMPT_TEMPLATE_MISSING")
    no_label = {**CLASSIFY_DRAFT, "name": "缺类别字段", "field_map": {"label": "", "confidence": None, "reason": None}}
    api.error(api.post("/api/prompts", no_label), 422, "VALIDATION_ERROR")
    text_mode = {**no_label, "name": "纯文本可以不填字段", "output_mode": "text"}
    assert api.ok(api.post("/api/prompts", text_mode), 201)["output_mode"] == "text"


def test_prompt_versions_restore_copy_delete(api: Api) -> None:
    created = api.ok(api.post("/api/prompts", {**CLASSIFY_DRAFT, "name": "版本测试", "note": "第一版"}), 201)
    assert created["version"] == 1 and created["is_builtin"] is False
    api.error(api.post("/api/prompts", {**CLASSIFY_DRAFT, "name": "版本测试"}), 409, "PROMPT_NAME_TAKEN")

    changed = api.ok(
        api.put(f"/api/prompts/{created['id']}", {**CLASSIFY_DRAFT, "name": "版本测试", "user_template": "文本：{{text}}"})
    )
    assert changed["version"] == 2
    renamed = api.ok(
        api.put(f"/api/prompts/{created['id']}", {**CLASSIFY_DRAFT, "name": "版本测试改名", "user_template": "文本：{{text}}"})
    )
    assert renamed["version"] == 2 and renamed["name"] == "版本测试改名"
    api.error(api.put(f"/api/prompts/{created['id']}", {**CLASSIFY_DRAFT, "task_type": "summarize", "name": "x"}), 422,
              "VALIDATION_ERROR")

    versions = api.ok(api.get(f"/api/prompts/{created['id']}/versions"))["items"]
    assert [v["version"] for v in versions] == [2, 1] and versions[1]["note"] == "第一版"
    v1 = api.ok(api.get(f"/api/prompts/{created['id']}/versions/1"))
    assert v1["snapshot"]["user_template"] == "{{text}}"
    restored = api.ok(api.post(f"/api/prompts/{created['id']}/restore", {"version": 1}))
    assert restored["version"] == 3 and restored["user_template"] == "{{text}}"
    assert api.ok(api.get(f"/api/prompts/{created['id']}/versions"))["items"][0]["note"] == "恢复自 v1"

    copy = api.ok(api.post("/api/prompts", {"copy_from_id": created["id"]}), 201)
    assert copy["name"] == "版本测试改名 副本" and copy["version"] == 1
    bad_copy = api.error(api.post("/api/prompts", {"copy_from_id": "x"}), 422, "VALIDATION_ERROR")
    assert bad_copy["detail"]["fields"][0]["path"] == "copy_from_id"
    assert api.delete(f"/api/prompts/{copy['id']}").status_code == 204
    api.error(api.post(f"/api/prompts/{created['id']}/reset-builtin"), 400, "BAD_REQUEST")


def test_builtin_prompt_protected_and_reset(api: Api) -> None:
    builtin = api.builtin_prompt("summarize")
    api.error(api.delete(f"/api/prompts/{builtin['id']}"), 409, "PROMPT_BUILTIN_PROTECTED")
    reset = api.ok(api.post(f"/api/prompts/{builtin['id']}/reset-builtin"))
    assert reset["version"] == builtin["version"] + 1
    assert api.ok(api.get(f"/api/prompts/{builtin['id']}/versions"))["items"][0]["note"] == "恢复内置默认"


def test_deleting_default_prompt_falls_back_to_builtin(fresh_api: Api) -> None:
    created = fresh_api.ok(fresh_api.post("/api/prompts", {**CLASSIFY_DRAFT, "name": "临时默认"}), 201)
    fresh_api.ok(fresh_api.patch("/api/settings", {"default_prompt_id": {"classify": created["id"]}}))
    assert fresh_api.delete(f"/api/prompts/{created['id']}").status_code == 204
    settings = fresh_api.ok(fresh_api.get("/api/settings"))
    assert settings["default_prompt_id"]["classify"] == fresh_api.builtin_prompt("classify")["id"]


def test_render_stages(api: Api) -> None:
    classify = api.builtin_prompt("classify")
    draft = {k: classify[k] for k in ("task_type", "system_prompt", "user_template", "output_mode", "field_map")}
    draft["user_template"] += "\n{{unknown_one}}"
    result = api.ok(api.post("/api/prompts/render", {"prompt": draft, "sample": {"kind": "text", "text": "我要投诉"}}))
    assert result["messages"][0]["role"] == "system"
    assert "我要投诉" in result["messages"][1]["content"]
    assert result["unknown_variables"] == ["{{unknown_one}}"]
    assert result["estimated_input_tokens"] > 0

    summarize = api.builtin_prompt("summarize")
    sdraft = {
        k: summarize[k]
        for k in ("task_type", "system_prompt", "user_template", "chunk_template", "merge_template", "output_mode", "field_map")
    }
    sample = {"kind": "text", "text": "第一段\n第二段"}
    main = api.ok(api.post("/api/prompts/render", {"prompt": sdraft, "sample": sample}))
    assert "[1] 第一段\n[2] 第二段" in main["messages"][-1]["content"]
    chunk = api.ok(api.post("/api/prompts/render", {"prompt": sdraft, "sample": sample, "stage": "chunk"}))
    assert "第 1 部分，共 1 部分" in chunk["messages"][-1]["content"]
    merge = api.ok(api.post("/api/prompts/render", {"prompt": sdraft, "sample": sample, "stage": "merge"}))
    assert "第 1 部分：" in merge["messages"][-1]["content"]


def test_draft_api_key_semantics(api: Api, server: LiveServer) -> None:
    """04 第 4 节：test-draft、list-remote 不传或空字符串时用 model_id 已保存的密钥，null 表示无密钥，非空用这个值。"""
    import asyncio

    from app.schemas.models import ModelDraftRequest
    from app.services import model_service

    saved = api.mock_model("草稿密钥", api_key="sk-saved-key-00001234")
    draft = {"name": "草稿", "base_url": f"{server.base_url}/mock/v1", "model": "wenshu-demo"}

    def key_for(body: dict[str, Any]) -> str | None:
        request = ModelDraftRequest.model_validate(body)
        coro = model_service.draft_spec(server.ctx.db, server.ctx.crypto, request)
        return asyncio.run_coroutine_threadsafe(coro, server.app.state.loop).result(timeout=10).api_key

    assert key_for({"config": draft, "model_id": saved["id"]}) == "sk-saved-key-00001234"
    assert key_for({"config": {**draft, "api_key": ""}, "model_id": saved["id"]}) == "sk-saved-key-00001234"
    assert key_for({"config": {**draft, "api_key": None}, "model_id": saved["id"]}) is None
    assert key_for({"config": {**draft, "api_key": "sk-typed"}, "model_id": saved["id"]}) == "sk-typed"
    assert key_for({"config": draft}) is None
    assert api.ok(api.post("/api/models/test-draft", {"config": draft, "model_id": saved["id"]}))["ok"] is True


def test_static_files_served_before_spa_fallback(tmp_path: Path) -> None:
    """04 第 12 节：static 里存在的文件（如 /favicon.svg）直接返回，不回退成 index.html；防止 .. 跳出 static。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.static import build_static_router

    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>文枢</title>", encoding="utf-8")
    (static / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (static / "assets" / "app-1a2b.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("不能读到", encoding="utf-8")
    mini = FastAPI()
    mini.include_router(build_static_router(static))
    with TestClient(mini) as http:
        icon = http.get("/favicon.svg")
        assert icon.status_code == 200 and icon.headers["content-type"].startswith("image/svg+xml")
        script = http.get("/assets/app-1a2b.js")
        assert script.headers["content-type"].startswith("text/javascript")
        page = http.get("/jobs/12")
        assert page.status_code == 200 and "<title>文枢</title>" in page.text
        escaped = http.get("/..%2Fsecret.txt")
        assert "不能读到" not in escaped.text
        assert http.get("/docs-assets/nothing.js").status_code == 404


def test_docs_page_is_offline(api: Api) -> None:
    """/docs 不从 CDN 加载：脚本和样式来自后端的 /docs-assets/，并带 Authorize 用的安全方案。"""
    page = api.get("/docs")
    assert page.status_code == 200
    assert "/docs-assets/swagger-ui-bundle.js" in page.text and "/docs-assets/swagger-ui.css" in page.text
    assert "cdn.jsdelivr.net" not in page.text and "unpkg.com" not in page.text
    assert '"persistAuthorization": true' in page.text
    bundle = api.get("/docs-assets/swagger-ui-bundle.js")
    assert bundle.status_code == 200 and bundle.headers["content-type"].startswith("text/javascript")
    schema = api.ok(api.get("/openapi.json"))
    scheme = schema["components"]["securitySchemes"]["WenShuClient"]
    assert scheme == {**scheme, "type": "apiKey", "in": "header", "name": "X-WenShu-Client"}
    assert schema["security"] == [{"WenShuClient": []}]
    names = schema["components"]["schemas"]
    for name in ("JobSummary", "JobLive", "JobDeletedEvent", "ItemsUpdatedEvent", "TracksUpdatedEvent", "PingEvent",
                 "PlaygroundStageEvent", "PlaygroundDeltaEvent", "PlaygroundDone", "PlaygroundErrorEvent"):
        assert name in names, name
    assert "/api/_dev/reset" in schema["paths"]
