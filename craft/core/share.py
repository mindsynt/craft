"""
分享系统 - 移植自 packages/opencode/src/share/
会话分享、导出、导入、ShareNext 同步
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from craft.core.session import sessions


class SharedSession:
    def __init__(self, session_id: str, visibility: str = "link"):
        self.id = f"share_{uuid.uuid4().hex[:12]}"
        self.session_id = session_id
        self.visibility = visibility
        self.created_at = time.time()
        self.view_count = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class ShareManager:
    def __init__(self):
        self._shares: dict[str, SharedSession] = {}

    def share(self, session_id: str, visibility: str = "link") -> SharedSession:
        share = SharedSession(session_id, visibility)
        self._shares[share.id] = share
        return share

    def get(self, share_id: str) -> SharedSession | None:
        share = self._shares.get(share_id)
        if share:
            share.view_count += 1
        return share

    def export_session(self, session_id: str) -> dict:
        s = sessions.get(session_id)
        if not s:
            return {"error": "会话不存在"}
        return {
            "version": "1.0",
            "type": "craft_session",
            "title": s.title,
            "messages": s.messages,
            "agent_id": s.agent_id,
            "model": s.model,
            "exported_at": time.time(),
        }

    def import_session(self, data: dict) -> str | None:
        if data.get("type") != "craft_session":
            return None
        s = sessions.create(
            title=data.get("title", "导入的会话"),
            agent_id=data.get("agent_id", "build"),
        )
        for msg in data.get("messages", []):
            s.add_message(msg.get("role", "user"), msg.get("content", ""))
        return s.id


share_manager = ShareManager()


# ── ShareNext (对应 share-next.ts) ──────────────────────────

# 是否禁用分享功能
SHARE_DISABLED = False


@dataclass
class ShareNextApi:
    """ShareNext API 路由"""
    create: str = "/api/shares"
    sync: str = "/api/shares/{share_id}/sync"
    remove: str = "/api/shares/{share_id}"
    data: str = "/api/shares/{share_id}/data"


@dataclass
class ShareNextReq:
    """ShareNext 请求配置"""
    headers: dict[str, str] = field(default_factory=dict)
    api: ShareNextApi = field(default_factory=ShareNextApi)
    base_url: str = "https://opncd.ai"


@dataclass
class ShareNextData:
    """ShareNext 同步数据类型"""
    type: str  # "session" | "message" | "part" | "session_diff" | "model"
    data: Any = None


@dataclass
class ShareInfo:
    """分享信息"""
    id: str = ""
    url: str = ""
    secret: str = ""

