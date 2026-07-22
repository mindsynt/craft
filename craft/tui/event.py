"""
TUI 事件定义 — 移植自 event.ts

TUI 系统内部事件类型定义。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class TuiEventType:
    """TUI 事件类型常量"""
    PROMPT_APPEND = "tui.prompt.append"
    COMMAND_EXECUTE = "tui.command.execute"
    TOAST_SHOW = "tui.toast.show"
    SESSION_SELECT = "tui.session.select"
    INSTRUCTIONS_LOADED = "tui.instructions.loaded"


class TuiEvent:
    """TUI 事件创建辅助"""

    @staticmethod
    def prompt_append(text: str) -> dict:
        return {"type": TuiEventType.PROMPT_APPEND, "text": text}

    @staticmethod
    def command_execute(command: str) -> dict:
        return {"type": TuiEventType.COMMAND_EXECUTE, "command": command}

    @staticmethod
    def toast_show(title: Optional[str], message: str,
                   variant: str = "info", duration: int = 5000) -> dict:
        event = {
            "type": TuiEventType.TOAST_SHOW,
            "message": message,
            "variant": variant,
        }
        if title:
            event["title"] = title
        if duration != 5000:
            event["duration"] = duration
        return event

    @staticmethod
    def session_select(session_id: str) -> dict:
        return {"type": TuiEventType.SESSION_SELECT, "sessionID": session_id}

    @staticmethod
    def instructions_loaded(files: list[str]) -> dict:
        return {"type": TuiEventType.INSTRUCTIONS_LOADED, "files": files}
