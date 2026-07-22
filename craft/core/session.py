"""会话系统"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from craft.config import CONFIG_DIR


class Session:
    def __init__(self, id: str = "", title: str = "新对话", agent_id: str = "build", model: str = ""):
        self.id = id or f"ses_{uuid.uuid4().hex[:12]}"
        self.title = title; self.agent_id = agent_id; self.model = model
        self.messages: list[dict] = []
        self.created_at = time.time(); self.updated_at = time.time()

    def add_message(self, role: str, content: str, **kw):
        self.messages.append({"role": role, "content": content, "timestamp": time.time(), **kw})
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "agent_id": self.agent_id,
                "model": self.model, "messages": self.messages,
                "created_at": self.created_at, "updated_at": self.updated_at,
                "message_count": len(self.messages)}


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._current_id: str | None = None; self._load()

    def _load(self):
        try:
            f = CONFIG_DIR / "sessions.json"
            if f.exists():
                data = json.loads(f.read_text())
                for sid, info in data.get("sessions", {}).items():
                    s = Session(id=sid); s.__dict__.update(info); self._sessions[sid] = s
                self._current_id = data.get("current_id")
        except Exception: pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        Path(CONFIG_DIR / "sessions.json").write_text(json.dumps(
            {"current_id": self._current_id,
             "sessions": {sid: s.to_dict() for sid, s in self._sessions.items()}},
            indent=2, default=str))

    def create(self, title: str = "新对话", agent_id: str = "build", model: str = "") -> Session:
        s = Session(title=title, agent_id=agent_id, model=model)
        self._sessions[s.id] = s; self._current_id = s.id; self._save(); return s

    def get(self, session_id: str) -> Session | None: return self._sessions.get(session_id)
    def current(self) -> Session | None: return self._sessions.get(self._current_id) if self._current_id else None
    def set_current(self, session_id: str):
        if session_id in self._sessions: self._current_id = session_id; self._save()

    def list(self, limit: int = 50) -> list[dict]:
        return sorted((s.to_dict() for s in self._sessions.values()),
                     key=lambda x: x["updated_at"], reverse=True)[:limit]

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            if self._current_id == session_id:
                self._current_id = next(iter(self._sessions)).id if self._sessions else None
            self._save(); return True
        return False


sessions = SessionManager()
