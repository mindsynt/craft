"""
企业版 — 移植自 packages/enterprise/
SSO 单点登录、审计日志、团队管理、用量统计
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR

logger = logging.getLogger(__name__)

ENTERPRISE_DB = CONFIG_DIR / "enterprise.json"


class AuditEntry:
    def __init__(self, action: str, user: str, resource: str, detail: str = ""):
        self.id = f"audit_{uuid.uuid4().hex[:12]}"
        self.action = action
        self.user = user
        self.resource = resource
        self.detail = detail
        self.ip = ""
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Team:
    def __init__(self, name: str, owner: str = ""):
        self.id = f"team_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.owner = owner
        self.members: list[str] = []
        self.created_at = time.time()


class EnterpriseManager:
    def __init__(self):
        self._teams: dict[str, Team] = {}
        self._audit_log: list[AuditEntry] = []
        self._sso_enabled = False
        self._sso_provider = ""
        self._load()

    def _db(self) -> Path:
        return CONFIG_DIR / "enterprise.json"

    def _load(self):
        try:
            f = self._db()
            if f.exists():
                data = json.loads(f.read_text())
                self._sso_enabled = data.get("sso_enabled", False)
                self._sso_provider = data.get("sso_provider", "")
                for item in data.get("teams", []):
                    team = Team("")
                    team.__dict__.update(item)
                    self._teams[team.id] = team
                for item in data.get("audit_log", []):
                    entry = AuditEntry("", "", "")
                    entry.__dict__.update(item)
                    self._audit_log.append(entry)
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._db().write_text(json.dumps({
            "sso_enabled": self._sso_enabled,
            "sso_provider": self._sso_provider,
            "teams": [t.__dict__ for t in self._teams.values()],
            "audit_log": [e.to_dict() for e in self._audit_log[-1000:]],
        }, indent=2, default=str))

    # SSO
    def configure_sso(self, provider: str, enabled: bool = True):
        self._sso_provider = provider
        self._sso_enabled = enabled
        self._save()
        logger.info(f"[Enterprise] SSO 配置: {provider} ({'启用' if enabled else '禁用'})")

    @property
    def sso_configured(self) -> bool:
        return self._sso_enabled and bool(self._sso_provider)

    # 审计
    def audit(self, action: str, user: str, resource: str, detail: str = ""):
        entry = AuditEntry(action, user, resource, detail)
        self._audit_log.append(entry)
        self._save()

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        return [e.to_dict() for e in self._audit_log[-limit:]]

    # 团队
    def create_team(self, name: str, owner: str = "") -> Team:
        team = Team(name, owner)
        self._teams[team.id] = team
        self._save()
        self.audit("team.create", owner, team.id, f"创建团队: {name}")
        return team

    def get_team(self, team_id: str) -> Team | None:
        return self._teams.get(team_id)

    def list_teams(self) -> list[Team]:
        return list(self._teams.values())

    def add_member(self, team_id: str, user_id: str):
        team = self._teams.get(team_id)
        if team and user_id not in team.members:
            team.members.append(user_id)
            self._save()

    def remove_member(self, team_id: str, user_id: str):
        team = self._teams.get(team_id)
        if team and user_id in team.members:
            team.members.remove(user_id)
            self._save()

    # 用量
    def get_usage_stats(self) -> dict:
        return {
            "total_users": len(set(e.user for e in self._audit_log)),
            "total_actions": len(self._audit_log),
            "teams_count": len(self._teams),
            "sso_enabled": self._sso_enabled,
        }


enterprise = EnterpriseManager()
