"""模型调用（05 第 1、6 节；08 第 10.1 节“模型调用”）。"""

from __future__ import annotations

import pytest

from app.services.llm_client import is_context_too_long

from .conftest import Api

PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def test_context_too_long_detection() -> None:
    """05 第 6.1 节：含上下文相关的说法才算 CONTEXT_TOO_LONG；含 max_tokens 的是最大输出参数超限，不误伤。"""
    assert is_context_too_long("This model's maximum context length is 8192 tokens")
    assert is_context_too_long("Error: context_length_exceeded")
    assert is_context_too_long("Input is too long for requested model.")
    assert is_context_too_long("prompt is too long: 210000 tokens > 200000 maximum")
    assert is_context_too_long("请求超出上下文长度限制")
    assert not is_context_too_long("max_tokens is too large: 9000. This model supports at most 8192 completion tokens")
    assert not is_context_too_long("Invalid max_completion_tokens: exceeds the maximum context length")
    assert not is_context_too_long("Invalid value for temperature")
    assert not is_context_too_long("")


def test_proxy_environment_is_ignored(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """设置了 HTTPS_PROXY 等环境变量时，proxy_url 为空的模型仍然直连（trust_env=False，05 第 1.1 节）。"""
    for name in PROXY_VARIABLES:
        monkeypatch.setenv(name, "http://127.0.0.1:9")   # 一个不会有人监听的端口
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    model = api.mock_model("测试-直连", "fast")
    result = api.ok(api.post(f"/api/models/{model['id']}/test"))
    assert result["ok"] is True, result
    demo = api.demo_model_id()
    assert api.ok(api.post(f"/api/models/{demo}/test"))["ok"] is True


def test_proxy_url_scheme_validation(api: Api) -> None:
    """只支持 http:// 和 https:// 代理；空字符串表示直连。"""
    base = {"base_url": f"{api.server.base_url}/mock/v1", "model": "wenshu-demo"}
    api.error(api.post("/api/models", {**base, "name": "socks 代理", "proxy_url": "socks5://127.0.0.1:1080"}),
              422, "VALIDATION_ERROR")
    direct = api.ok(api.post("/api/models", {**base, "name": "直连", "proxy_url": ""}), 201)
    assert direct["proxy_url"] is None
    proxied = api.ok(api.post("/api/models", {**base, "name": "走代理", "proxy_url": "http://127.0.0.1:7890"}), 201)
    assert proxied["proxy_url"] == "http://127.0.0.1:7890"
