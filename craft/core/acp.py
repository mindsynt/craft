"""
ACP 协议 — 移植自 packages/opencode/src/acp/
Agent 间通信协议
"""

from __future__ import annotations

import json
import uuid
from typing import Any


class AgentMessage:
    def __init__(self, type: str, payload: dict | None = None,
                 sender: str = "", target: str = ""):
        self.id = uuid.uuid4().hex[:12]
        self.type = type
        self.payload = payload or {}
        self.sender = sender
        self.target = target
        self.version = "1.0"

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id, "type": self.type, "payload": self.payload,
            "sender": self.sender, "target": self.target, "version": self.version,
        })

    @staticmethod
    def from_json(text: str) -> AgentMessage:
        data = json.loads(text)
        msg = AgentMessage(data.get("type", ""), data.get("payload", {}),
                          data.get("sender", ""), data.get("target", ""))
        msg.id = data.get("id", msg.id)
        return msg


class AgentProtocol:
    def __init__(self):
        self._listeners: dict[str, list] = {}

    def on(self, msg_type: str, handler):
        self._listeners.setdefault(msg_type, []).append(handler)

    async def handle_message(self, text: str) -> str | None:
        msg = AgentMessage.from_json(text)
        responses = []
        for handler in self._listeners.get(msg.type, []):
            r = handler(msg)
            if hasattr(r, "__await__"):
                r = await r
            if r:
                responses.append(str(r))
        return responses[0] if responses else None

    def create_message(self, type: str, payload: dict | None = None,
                       sender: str = "", target: str = "") -> AgentMessage:
        return AgentMessage(type, payload, sender, target)


acp = AgentProtocol()
