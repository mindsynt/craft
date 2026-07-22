"""
收件箱/通知系统 — 移植自 packages/opencode/src/inbox/
通知管理、消息队列、实时推送
"""

from __future__ import annotations

import json
import time
import uuid

from craft.config import CONFIG_DIR

INBOX_DB = CONFIG_DIR / "inbox.json"


class InboxMessage:
    def __init__(self, type: str = "info", title: str = "", content: str = "",
                 source: str = "system", actionable: bool = False):
        self.id = f"msg_{uuid.uuid4().hex[:12]}"
        self.type = type  # info / success / warning / error
        self.title = title
        self.content = content
        self.source = source
        self.actionable = actionable
        self.read = False
        self.created_at = time.time()

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class Inbox:
    def __init__(self):
        self._messages: list[InboxMessage] = []
        self._load()

    def _load(self):
        try:
            if INBOX_DB.exists():
                data = json.loads(INBOX_DB.read_text())
                for item in data:
                    msg = InboxMessage()
                    msg.__dict__.update(item)
                    self._messages.append(msg)
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        INBOX_DB.write_text(json.dumps(
            [m.to_dict() for m in self._messages], indent=2, default=str
        ))

    def add(self, type: str = "info", title: str = "", content: str = "",
            source: str = "system", actionable: bool = False) -> str:
        msg = InboxMessage(type, title, content, source, actionable)
        self._messages.insert(0, msg)
        self._save()
        return msg.id

    def list(self, unread_only: bool = False, limit: int = 50) -> list[dict]:
        msgs = [m for m in self._messages if not unread_only or not m.read]
        return [m.to_dict() for m in msgs[:limit]]

    def mark_read(self, msg_id: str) -> bool:
        for m in self._messages:
            if m.id == msg_id:
                m.read = True
                self._save()
                return True
        return False

    def mark_all_read(self):
        for m in self._messages:
            m.read = True
        self._save()

    def unread_count(self) -> int:
        return sum(1 for m in self._messages if not m.read)

    def clear(self):
        self._messages.clear()
        self._save()


inbox = Inbox()
