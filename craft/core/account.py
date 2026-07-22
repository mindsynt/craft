"""
账户系统 — 移植自 packages/opencode/src/account/
多账户管理、组织/工作空间、账户切换
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


class Organization:
    def __init__(self, id: str, name: str, plan: str = "free"):
        self.id = id
        self.name = name
        self.plan = plan
        self.created_at = time.time()


class Account:
    def __init__(self, id: str, email: str = "", name: str = "",
                 provider: str = "local", token: str = ""):
        self.id = id or f"acc_{uuid.uuid4().hex[:12]}"
        self.email = email
        self.name = name or email
        self.provider = provider
        self.token = token
        self.organization: Organization | None = None
        self.preferences: dict[str, Any] = {}
        self.created_at = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id, "email": self.email, "name": self.name,
            "provider": self.provider, "organization": self.organization.__dict__ if self.organization else None,
            "preferences": self.preferences, "created_at": self.created_at,
        }


class AccountManager:
    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self._current_id: str | None = None
        self._load()

    def _db(self) -> Path:
        return CONFIG_DIR / "accounts.json"

    def _load(self):
        try:
            f = self._db()
            if f.exists():
                data = json.loads(f.read_text())
                for aid, info in data.get("accounts", {}).items():
                    acc = Account(id=aid)
                    acc.__dict__.update(info)
                    if info.get("organization"):
                        org = Organization("", "")
                        org.__dict__.update(info["organization"])
                        acc.organization = org
                    self._accounts[aid] = acc
                self._current_id = data.get("current_id")
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "current_id": self._current_id,
            "accounts": {aid: acc.to_dict() for aid, acc in self._accounts.items()},
        }
        self._db().write_text(json.dumps(data, indent=2, default=str))

    def create(self, email: str, name: str = "", provider: str = "local") -> Account:
        acc = Account(id=f"acc_{uuid.uuid4().hex[:12]}", email=email, name=name, provider=provider)
        self._accounts[acc.id] = acc
        self._current_id = acc.id
        self._save()
        return acc

    def get(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    def current(self) -> Account | None:
        if self._current_id:
            return self._accounts.get(self._current_id)
        return None

    def set_current(self, account_id: str):
        if account_id in self._accounts:
            self._current_id = account_id
            self._save()

    def list(self) -> list[Account]:
        return list(self._accounts.values())

    def delete(self, account_id: str) -> bool:
        if account_id in self._accounts:
            del self._accounts[account_id]
            if self._current_id == account_id:
                self._current_id = next(iter(self._accounts)).id if self._accounts else None
            self._save()
            return True
        return False

    def set_organization(self, account_id: str, org: Organization):
        acc = self._accounts.get(account_id)
        if acc:
            acc.organization = org
            self._save()

    def set_preference(self, account_id: str, key: str, value: Any):
        acc = self._accounts.get(account_id)
        if acc:
            acc.preferences[key] = value
            self._save()


accounts = AccountManager()
