"""
团队管理 — 移植自 packages/opencode/src/team/
团队、成员、角色、权限
"""

from __future__ import annotations

import json
import time
import uuid

from craft.config import CONFIG_DIR


class TeamMember:
    def __init__(self, user_id: str, role: str = "member", name: str = ""):
        self.user_id = user_id
        self.role = role
        self.name = name
        self.joined_at = time.time()


class Team:
    def __init__(self, name: str, owner_id: str = ""):
        self.id = f"team_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.owner_id = owner_id
        self.members: list[TeamMember] = []
        self.created_at = time.time()

    def add_member(self, user_id: str, role: str = "member", name: str = ""):
        if not any(m.user_id == user_id for m in self.members):
            self.members.append(TeamMember(user_id, role, name))

    def remove_member(self, user_id: str):
        self.members = [m for m in self.members if m.user_id != user_id]

    def is_member(self, user_id: str) -> bool:
        return any(m.user_id == user_id for m in self.members)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "owner_id": self.owner_id,
                "members": [{"user_id": m.user_id, "role": m.role, "name": m.name}
                           for m in self.members],
                "created_at": self.created_at}


class TeamManager:
    def __init__(self):
        self._teams: dict[str, Team] = {}
        self._db_path = CONFIG_DIR / "teams.json"
        self._load()

    def _load(self):
        try:
            if self._db_path.exists():
                for item in json.loads(self._db_path.read_text()):
                    t = Team("")
                    t.__dict__.update(item)
                    self._teams[t.id] = t
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._db_path.write_text(json.dumps(
            [t.to_dict() for t in self._teams.values()], indent=2, default=str
        ))

    def create(self, name: str, owner_id: str = "") -> Team:
        team = Team(name, owner_id)
        self._teams[team.id] = team
        self._save()
        return team

    def get(self, team_id: str) -> Team | None:
        return self._teams.get(team_id)

    def list(self) -> list[Team]:
        return list(self._teams.values())

    def delete(self, team_id: str) -> bool:
        if team_id in self._teams:
            del self._teams[team_id]
            self._save()
            return True
        return False


team_manager = TeamManager()
