"""API Key 加解密与掩码（02 第 10 节）。

Fernet 加密后存库，加密密钥在 data/secret.key（首次启动生成）。删除 secret.key 会使已保存的 API Key 失效。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class Crypto:
    def __init__(self, key_file: Path) -> None:
        self.key_file = key_file
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self.key_file.is_file():
            key = self.key_file.read_bytes().strip()
            if key:
                return key
        key = Fernet.generate_key()
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.key_file.with_suffix(".tmp")
        tmp.write_bytes(key)
        os.replace(tmp, self.key_file)
        logger.info("已生成新的加密密钥 secret.key")
        return key

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str | None) -> str | None:
        """解密失败（例如 secret.key 被换掉）时返回 None，调用方按“无密钥”处理。"""
        if not token:
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            logger.warning("API Key 无法解密：secret.key 可能已被替换，请重新填写密钥")
            return None


def last4(api_key: str) -> str:
    """掩码用的末 4 位；太短的密钥不保留任何字符，避免泄露一半内容。"""
    return api_key[-4:] if len(api_key) >= 8 else ""


def mask(api_key_plain: str | None, stored_last4: str | None) -> str:
    """例如 'sk-…3f9a'：保留形如 “sk-” 的短前缀和末 4 位。"""
    prefix = ""
    if api_key_plain and "-" in api_key_plain[:5] and len(api_key_plain) >= 12:
        prefix = api_key_plain[: api_key_plain.index("-") + 1]
    return f"{prefix}…{stored_last4 or ''}"
