"""TUI 路由 — 移植自 routes/instance/tui.ts

TUI 控制路由：提示追加、命令执行、会话选择、Toast 通知等。
"""

from __future__ import annotations

import logging
from typing import Any

from craft.core.server.event import EventBus, global_bus

logger = logging.getLogger(__name__)


class TuiRoutes:
    """TUI 路由处理器

    对应 TS TuiRoutes
    """

    @staticmethod
    async def append_prompt(request: Any) -> Any:
        """POST /tui/append-prompt

        追加 TUI 提示。
        """
        body = await _get_json_body(request)
        global_bus.emit("tui.prompt.append", body or {})
        return True

    @staticmethod
    async def open_help(request: Any) -> Any:
        """POST /tui/open-help

        打开帮助对话框。
        """
        global_bus.emit("tui.command.execute", {"command": "help.show"})
        return True

    @staticmethod
    async def open_sessions(request: Any) -> Any:
        """POST /tui/open-sessions

        打开会话对话框。
        """
        global_bus.emit("tui.command.execute", {"command": "session.list"})
        return True

    @staticmethod
    async def open_themes(request: Any) -> Any:
        """POST /tui/open-themes

        打开主题对话框。
        """
        global_bus.emit("tui.command.execute", {"command": "theme.list"})
        return True

    @staticmethod
    async def open_models(request: Any) -> Any:
        """POST /tui/open-models

        打开模型对话框。
        """
        global_bus.emit("tui.command.execute", {"command": "model.list"})
        return True

    @staticmethod
    async def submit_prompt(request: Any) -> Any:
        """POST /tui/submit-prompt

        提交提示。
        """
        global_bus.emit("tui.command.execute", {"command": "prompt.submit"})
        return True

    @staticmethod
    async def clear_prompt(request: Any) -> Any:
        """POST /tui/clear-prompt

        清除提示。
        """
        global_bus.emit("tui.command.execute", {"command": "prompt.clear"})
        return True

    @staticmethod
    async def execute_command(request: Any) -> Any:
        """POST /tui/execute-command

        执行 TUI 命令。
        """
        body = await _get_json_body(request)
        command = (body or {}).get("command", "")

        command_map = {
            "session_new": "session.new",
            "session_share": "session.share",
            "session_interrupt": "session.interrupt",
            "session_compact": "session.compact",
            "messages_page_up": "session.page.up",
            "messages_page_down": "session.page.down",
            "messages_line_up": "session.line.up",
            "messages_line_down": "session.line.down",
            "messages_half_page_up": "session.half.page.up",
            "messages_half_page_down": "session.half.page.down",
            "messages_first": "session.first",
            "messages_last": "session.last",
            "agent_cycle": "agent.cycle",
        }

        mapped = command_map.get(command, command)
        global_bus.emit("tui.command.execute", {"command": mapped})
        return True

    @staticmethod
    async def show_toast(request: Any) -> Any:
        """POST /tui/show-toast

        显示 Toast 通知。
        """
        body = await _get_json_body(request)
        global_bus.emit("tui.toast.show", body or {})
        return True

    @staticmethod
    async def publish_event(request: Any) -> Any:
        """POST /tui/publish

        发布 TUI 事件。
        """
        body = await _get_json_body(request)
        if body:
            event_type = body.get("type", "")
            properties = body.get("properties", {})
            global_bus.emit(event_type, properties)
        return True

    @staticmethod
    async def select_session(request: Any) -> Any:
        """POST /tui/select-session

        选择会话。
        """
        body = await _get_json_body(request)
        if body:
            session_id = body.get("sessionID", "")
            global_bus.emit("tui.session.select", {"sessionID": session_id})
        return True


async def _get_json_body(request: Any) -> dict:
    """Extract JSON body from request (async)"""
    if hasattr(request, "json"):
        try:
            body = request.json()
            if callable(body):
                body = await body()
            if not isinstance(body, dict):
                return {}
            return body
        except Exception:
            pass
    return {}
