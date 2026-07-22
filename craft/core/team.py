"""
团队管理 — 移植自 packages/opencode/src/team/
团队创建、成员管理、角色分配、事件通知
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR
from craft.core.bus import define_event, bus


# ── 事件定义 ────────────────────────────────────────────────
# 对应 TS team/events.ts

TeamCreated = define_event("team.created", {
    "teamID": str,
    "creatorSessionID": str,
})

TeamMemberJoined = define_event("team.member.joined", {
    "teamID": str,
    "sessionID": str,
    "agent": str,
    "role": str,
})

TeamMemberLeft = define_event("team.member.left", {
    "teamID": str,
    "sessionID": str,
})


# ── Schema ──────────────────────────────────────────────────
# 对应 TS team/schema.ts

class TeamMember:
    """团队成员 — 对应 TS TeamMember schema"""
    def __init__(self, session_id: str, agent: str = "", role: str = "member",
                 name: str = "", joined_at: float | None = None):
        self.sessionID = session_id
        self.agent = agent
        self.role = role
        self.name = name
        self.joined_at = joined_at or time.time()

    def to_dict(self) -> dict:
        return {
            "sessionID": self.sessionID,
            "agent": self.agent,
            "role": self.role,
            "name": self.name,
            "joinedAt": self.joined_at,
        }

    @staticmethod
    def from_dict(d: dict) -> TeamMember:
        return TeamMember(
            session_id=d.get("sessionID", ""),
            agent=d.get("agent", ""),
            role=d.get("role", "member"),
            name=d.get("name", ""),
            joined_at=d.get("joinedAt", time.time()),
        )


class TeamMessage:
    """团队消息"""
    def __init__(self, id: str, from_session: str, from_agent: str, content: str,
                 to_session: str | None = None, timestamp: float | None = None):
        self.id = id
        self.from_session = from_session
        self.from_agent = from_agent
        self.to_session = to_session
        self.content = content
        self.timestamp = timestamp or time.time()


# ── Team ────────────────────────────────────────────────────

class Team:
    """团队 — 对应 TS Team schema"""

    def __init__(self, name: str, owner_id: str = ""):
        self.id = f"team_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.owner_id = owner_id
        self.members: list[dict] = []
        self.created_at = time.time()
        self.directory: str = ""

    def add_member(self, session_id: str, role: str = "member", name: str = "",
                   agent: str = ""):
        if not any(m.get("sessionID") == session_id for m in self.members):
            self.members.append({
                "sessionID": session_id,
                "role": role,
                "name": name,
                "agent": agent,
                "joinedAt": time.time(),
            })

    def remove_member(self, session_id: str):
        self.members = [m for m in self.members if m.get("sessionID") != session_id]

    def is_member(self, session_id: str) -> bool:
        return any(m.get("sessionID") == session_id for m in self.members)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "owner_id": self.owner_id,
            "members": list(self.members),
            "created_at": self.created_at,
            "directory": self.directory,
        }


# ── TeamManager ──────────────────────────────────────────────
# 对应 TS team/index.ts 的 Service

class TeamManager:
    """团队管理器 — 文件系统持久化 + 总线事件通知"""

    def __init__(self):
        self._teams: dict[str, Team] = {}
        self._db_path = CONFIG_DIR / "teams.json"
        self._load()

    def _load(self):
        try:
            if self._db_path.exists():
                data = json.loads(self._db_path.read_text())
                for item in data:
                    t = Team(item.get("name", ""))
                    t.id = item.get("id", t.id)
                    t.owner_id = item.get("owner_id", "")
                    t.members = item.get("members", [])
                    t.created_at = item.get("created_at", time.time())
                    t.directory = item.get("directory", "")
                    self._teams[t.id] = t
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._db_path.write_text(json.dumps(
            [t.to_dict() for t in self._teams.values()], indent=2, default=str
        ))

    def _resolve_team_dir(self, team_id: str, base_dir: str | None = None) -> str:
        """解析团队数据目录 — 对应 TS resolveTeamDir"""
        base = base_dir or str(CONFIG_DIR)
        return os.path.join(base, ".craft", "teams", team_id)

    def _members_file_path(self, team_id: str, base_dir: str | None = None) -> str:
        return os.path.join(self._resolve_team_dir(team_id, base_dir), "members.json")

    def _read_members_file(self, team_id: str, base_dir: str | None = None) -> list[dict]:
        """读取团队成员的 JSON 文件 — 对应 TS readMembersFile"""
        file_path = self._members_file_path(team_id, base_dir)
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
            return json.loads(raw)
        except Exception:
            return []

    def _write_members_file(self, team_id: str, members: list[dict],
                            base_dir: str | None = None):
        file_path = self._members_file_path(team_id, base_dir)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        Path(file_path).write_text(json.dumps(members, indent=2))

    def create(self, name: str, owner_id: str = "",
               creator_session_id: str = "", base_dir: str | None = None) -> Team:
        """创建团队 — 对应 TS Team.create

        Args:
            name: 团队名
            owner_id: 所有者 ID
            creator_session_id: 创建者会话 ID
            base_dir: 基础目录
        """
        team = Team(name, owner_id)
        dir_path = self._resolve_team_dir(team.id, base_dir)

        os.makedirs(dir_path, exist_ok=True)
        self._write_members_file(team.id, [], base_dir)

        team.directory = dir_path
        self._teams[team.id] = team
        self._save()

        # 发布事件
        bus.publish(TeamCreated["type"], {
            "teamID": team.id,
            "creatorSessionID": creator_session_id,
        })

        return team

    def add_member(self, team_id: str, session_id: str, agent: str = "",
                   role: str = "member", base_dir: str | None = None):
        """添加团队成员 — 对应 TS Team.addMember"""
        members = self._read_members_file(team_id, base_dir)
        existing = any(m.get("sessionID") == session_id for m in members)

        if not existing:
            members.append({
                "sessionID": session_id,
                "agent": agent,
                "role": role,
                "joinedAt": int(time.time() * 1000),
            })
            self._write_members_file(team_id, members, base_dir)

            # 同步到内存
            if team_id in self._teams:
                self._teams[team_id].add_member(session_id, role, agent=agent)

            # 发布事件
            bus.publish(TeamMemberJoined["type"], {
                "teamID": team_id,
                "sessionID": session_id,
                "agent": agent,
                "role": role,
            })

    def remove_member(self, team_id: str, session_id: str, base_dir: str | None = None):
        """移除团队成员 — 对应 TS Team.removeMember"""
        members = self._read_members_file(team_id, base_dir)
        filtered = [m for m in members if m.get("sessionID") != session_id]

        if len(filtered) != len(members):
            self._write_members_file(team_id, filtered, base_dir)

            # 同步到内存
            if team_id in self._teams:
                self._teams[team_id].remove_member(session_id)

            # 发布事件
            bus.publish(TeamMemberLeft["type"], {
                "teamID": team_id,
                "sessionID": session_id,
            })

    def get_members(self, team_id: str, base_dir: str | None = None) -> list[dict]:
        """获取团队成员列表 — 对应 TS Team.getMembers"""
        # 优先从文件中读取
        members = self._read_members_file(team_id, base_dir)
        if members:
            return members
        # 回退到内存
        team = self._teams.get(team_id)
        return team.members if team else []

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

    def team_dir(self, team_id: str, base_dir: str | None = None) -> str:
        """获取团队目录 — 对应 TS Team.teamDir"""
        return self._resolve_team_dir(team_id, base_dir)


team_manager = TeamManager()
