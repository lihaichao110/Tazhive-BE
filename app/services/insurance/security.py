"""投保个人资料的应用层加密与安全脱敏。"""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class PIIEncryptionError(RuntimeError):
    """加密配置缺失或密文损坏。"""


class PIICipher:
    """使用独立 Fernet 密钥加解密人员资料 JSON。"""

    def __init__(self, key: str | None):
        if not key:
            raise PIIEncryptionError("投保信息加密服务未配置")
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise PIIEncryptionError("投保信息加密密钥无效") from exc

    def encrypt(self, payload: dict[str, str]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        return self._fernet.encrypt(raw).decode("ascii")

    def decrypt(self, ciphertext: str) -> dict[str, str]:
        try:
            value: Any = json.loads(self._fernet.decrypt(ciphertext.encode("ascii")))
        except (InvalidToken, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise PIIEncryptionError("投保信息密文无法解密") from exc
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        ):
            raise PIIEncryptionError("投保信息密文结构无效")
        return value


def mask_name(name: str) -> str:
    """姓名只保留首字符，单字姓名完全隐藏。"""
    return f"{name[0]}{'*' * max(1, len(name) - 1)}" if name else "***"


def mask_mobile(mobile: str) -> str:
    return f"{mobile[:3]}****{mobile[-4:]}" if len(mobile) == 11 else "***"


def mask_id_number(id_number: str) -> str:
    return f"{id_number[:3]}***********{id_number[-4:]}" if len(id_number) == 18 else "***"
