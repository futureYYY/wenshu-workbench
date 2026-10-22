"""API Key 加解密与掩码；接口、日志、数据库里没有明文（02 第 10 节；08 第 10.1 节“加密”）。"""

from __future__ import annotations

from pathlib import Path

from app.services.crypto import Crypto, last4, mask

from .conftest import Api

SECRET = "sk-test-0123456789abcdef3f9a"


def test_roundtrip(tmp_path: Path) -> None:
    crypto = Crypto(tmp_path / "secret.key")
    token = crypto.encrypt(SECRET)
    assert SECRET not in token
    assert crypto.decrypt(token) == SECRET
    # 同一个 secret.key 重新加载仍可解密
    assert Crypto(tmp_path / "secret.key").decrypt(token) == SECRET


def test_wrong_key_returns_none(tmp_path: Path) -> None:
    token = Crypto(tmp_path / "a.key").encrypt(SECRET)
    assert Crypto(tmp_path / "b.key").decrypt(token) is None


def test_mask() -> None:
    assert mask(SECRET, last4(SECRET)) == "sk-…3f9a"
    assert mask("abcdefghijklmnop", last4("abcdefghijklmnop")) == "…mnop"
    assert last4("short") == ""


def test_no_plaintext_anywhere(fresh_api: Api) -> None:
    model = fresh_api.mock_model("密钥测试", api_key=SECRET)
    assert model["has_api_key"] is True
    assert model["api_key_masked"] == "sk-…3f9a"
    listing = fresh_api.get("/api/models", params={"include_demo": True}).text
    detail = fresh_api.get(f"/api/models/{model['id']}").text
    assert SECRET not in listing and SECRET not in detail
    # 用这个密钥实际发一次请求（测试连接），日志里也不能出现
    fresh_api.ok(fresh_api.post(f"/api/models/{model['id']}/test"))
    data_dir = fresh_api.server.data_dir
    for path in data_dir.rglob("*"):
        if path.is_file() and path.name != "secret.key":
            assert SECRET.encode() not in path.read_bytes(), f"{path} 里出现了明文密钥"


def test_patch_key_semantics(fresh_api: Api) -> None:
    """04 第 4 节：PATCH 时 api_key 不传和传空字符串都不改，传 null 清除，非空字符串替换。"""
    model = fresh_api.mock_model("密钥语义", api_key=SECRET)
    # 不传：不改
    same = fresh_api.ok(fresh_api.patch(f"/api/models/{model['id']}", {"notes": "改备注"}))
    assert same["has_api_key"] is True
    # 空字符串：等同于不传，不改（编辑表单里密钥框留空时不会误删）
    kept = fresh_api.ok(fresh_api.patch(f"/api/models/{model['id']}", {"api_key": ""}))
    assert kept["has_api_key"] is True and kept["api_key_masked"] == "sk-…3f9a"
    # 非空：替换
    replaced = fresh_api.ok(fresh_api.patch(f"/api/models/{model['id']}", {"api_key": "sk-new-key-000000009999"}))
    assert replaced["api_key_masked"] == "sk-…9999"
    # null：清除
    cleared = fresh_api.ok(fresh_api.patch(f"/api/models/{model['id']}", {"api_key": None}))
    assert cleared["has_api_key"] is False and cleared["api_key_masked"] is None
