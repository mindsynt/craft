"""TUI 路由 — 移植自 routes/instance/tui.ts

TUI 控制路由：提示追加、命令执行、会话选择、Toast 通知等。
"""

from __future__ import annotations

import logging
from typing import Any

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
        # TODO: 接入 Bus.publish(TuiEvent.PromptAppend)
        return True

    @staticmethod
    async def open_help(request: Any) -> Any:
        """POST /tui/open-help
        
        打开帮助对话框。
        """
        return True

    @staticmethod
    async def open_sessions(request: Any) -> Any:
        """POST /tui/open-sessions
        
        打开会话对话框。
        """
        return True

    @staticmethod
    async def open_themes(request: Any) -> Any:
        """POST /tui/open-themes
        
        打开主题对话框。
        """
        return True

    @staticmethod
    async def open_models(request: Any) -> Any:
        """POST /tui/open-models
        
        打开模型对话框。
        """
        return True

    @staticmethod
    async def submit_prompt(request: Any) -> Any:
        """POST /tui/submit-prompt
        
        提交提示。
        """
        return True

    @staticmethod
    async def clear_prompt(request: Any) -> Any:
        """POST /tui/clear-prompt
        
        清除提示。
        """
        return True

    @staticmethod
    async def execute_command(request: Any) -> Any:
        """POST /tui/execute-command
        
        执行 TUI 命令。
        """
        return True

    @staticmethod
    async def show_toast(request: Any) -> Any:
        """POST /tui/show-toast
        
        显示 Toast 通知。
        """
        return True

    @staticmethod
    async def publish_event(request: Any) -> Any:
        """POST /tui/publish
        
        发布 TUI 事件。
        """
        return True

    @staticmethod
    async def select_session(request: Any) -> Any:
        """POST /tui/select-session
        
        选择会话。
        """
        return True
