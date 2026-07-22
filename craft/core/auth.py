"""
认证系统 — 移植自 packages/opencode/src/auth/
支持 OAuth 令牌、API 密钥、WellKnown 认证；持久化到 auth.json
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


# ── 认证类型 ─────────────────────────────────────────────────

@dataclass
class OAuthInfo:
    """OAuth 2.0 认证信息"""
    type: str = "oauth"
    refresh: str = ""
    access: str = ""
    expires: float = 0
    accountId: str | None = None
    enterpriseUrl: str | None = None


@dataclass
class ApiKeyInfo:
    """API 密钥认证信息"""
    type: str = "api"
    key: str = ""
    metadata: dict[str, str] | None = None


@dataclass
class WellKnownInfo:
    """WellKnown 认证信息"""
    type: str = "wellknown"
    key: str = ""
    token: str = ""


# ── AuthError ────────────────────────────────────────────────

class AuthError(Exception):
    def __init__(self, message: str, cause: Any = None):
        self.message = message
        self.cause = cause
        super().__init__(message)


# ── AuthManager ──────────────────────────────────────────────

class AuthManager:
    """认证管理器 — 读取/写入 ~/.craft/auth.json

    支持三种认证类型: OAuth, API 密钥, WellKnown
    环境变量 MIMOCODE_AUTH_CONTENT 可覆盖持久化存储（用于测试）
    """

    def __init__(self):
        self._auth_file = CONFIG_DIR / "auth.json"
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self):
        """从 auth.json 或环境变量加载认证数据"""
        env_content = os.environ.get("MIMOCODE_AUTH_CONTENT")
        if env_content:
            try:
                self._data = json.loads(env_content)
                return
            except Exception:
                pass

        try:
            if self._auth_file.exists():
                self._data = json.loads(self._auth_file.read_text())
        except Exception:
            self._data = {}

    def _save(self):
        """持久化认证数据到 auth.json，权限 0o600"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._auth_file.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
        os.chmod(self._auth_file, 0o600)

    def _normalize_key(self, key: str) -> str:
        """标准化 provider key：去除尾部斜杠"""
        return key.rstrip("/")

    def get(self, provider_id: str) -> dict | None:
        """获取指定 provider 的认证信息"""
        norm = self._normalize_key(provider_id)
        return self._data.get(norm)

    def all(self) -> dict[str, dict]:
        """获取所有认证信息"""
        return dict(self._data)

    def set(self, key: str, info: dict):
        """设置认证信息

        标准化 key，清除旧的冗余条目
        """
        norm = self._normalize_key(key)
        if norm != key:
            self._data.pop(key, None)
        self._data.pop(norm + "/", None)
        self._data[norm] = info
        self._save()

    def remove(self, key: str):
        """移除认证信息"""
        norm = self._normalize_key(key)
        self._data.pop(key, None)
        self._data.pop(norm, None)
        self._save()

    # ── 便捷方法 ───────────────────────────────────────────

    def get_api_key(self, provider: str) -> str | None:
        """获取 API 密钥（优先环境变量）"""
        env_key = os.environ.get(f"{provider.upper()}_API_KEY")
        if env_key:
            return env_key

        info = self.get(provider)
        if not info:
            return None
        if info.get("type") == "api":
            return info.get("key")
        if info.get("type") == "oauth":
            return info.get("access")
        if info.get("type") == "wellknown":
            return info.get("token")
        return info.get("token") or info.get("key")

    def list_providers(self) -> list[str]:
        """列出所有已配置的 provider"""
        return list(self._data.keys())


auth = AuthManager()
