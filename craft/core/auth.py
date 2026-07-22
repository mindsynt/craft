"""认证系统"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from craft.config import CONFIG_DIR


class AuthToken:
    def __init__(self, provider: str, token: str, expires_at: float = 0, email: str = "", name: str = ""):
        self.provider = provider; self.token = token; self.expires_at = expires_at
        self.email = email; self.name = name

    @property
    def expired(self) -> bool: return self.expires_at > 0 and time.time() > self.expires_at

    @property
    def valid(self) -> bool: return bool(self.token) and not self.expired


class AuthManager:
    def __init__(self):
        self._tokens: dict[str, AuthToken] = {}
        self._load()

    def _load(self):
        try:
            f = CONFIG_DIR / "auth.json"
            if f.exists():
                for p, i in json.loads(f.read_text()).items():
                    self._tokens[p] = AuthToken(**i)
        except Exception: pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {p: {"provider": t.provider, "token": t.token, "expires_at": t.expires_at,
                    "email": t.email, "name": t.name} for p, t in self._tokens.items()}
        Path(CONFIG_DIR / "auth.json").write_text(json.dumps(data, indent=2))

    def set_token(self, provider: str, token: str, **kw):
        self._tokens[provider] = AuthToken(provider=provider, token=token, **kw)
        self._save()

    def get_api_key(self, provider: str) -> str | None:
        env = os.environ.get(f"{provider.upper()}_API_KEY")
        if env: return env
        t = self._tokens.get(provider)
        return t.token if t and t.valid else None

    def list_providers(self) -> list[str]: return list(self._tokens.keys())


auth = AuthManager()
