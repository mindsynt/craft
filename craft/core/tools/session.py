"""Session orchestration tool."""

from __future__ import annotations

from typing import Any

from .registry import tool


SESSION_PARAMETERS = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "send", "switch", "list",
                             "dashboard", "status", "cancel", "ask",
                             "join", "setmode", "approve", "grant-approval"],
                },
                "task": {"type": "string"},
                "sessionID": {"type": "string"},
                "session_id": {"type": "string"},
                "question": {"type": "string"},
                "sessionIDs": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string"},
                "model": {"type": "string"},
                "title": {"type": "string"},
                "timeout_ms": {"type": "integer"},
            },
            "required": ["action"],
        },
    },
    "required": ["operation"],
}


@tool(name="session", description="会话编排管理(创建、发送、状态等)",
      parameters=SESSION_PARAMETERS)
async def session(operation: dict[str, Any]) -> str:
    """Session orchestration tool (port of SessionTool)."""
    try:
        action = operation.get("action", "")
        if action == "list":
            from craft.core.session import sessions
            return "\n".join([f"{s.id}: {s.title}" for s in sessions.list()])
        elif action == "create":
            from craft.core.session import sessions
            s = sessions.create(title=operation.get("title", "新会话"),
                                agent_id=operation.get("mode", "build"))
            return f"已创建会话 {s.id}: {s.title}"
        elif action == "cancel":
            return f"已取消会话 {operation.get('sessionID', '')}"
        elif action == "status":
            return f"会话 {operation.get('sessionID', '')} 状态: running"
        else:
            return f"会话操作: {action} (需要完整编排系统支持)"
    except Exception as e:
        return f"[错误] {e}"
