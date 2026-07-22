"""
首页 — 移植 routes/home.tsx + ui/home/ 系列
"""

from __future__ import annotations
from textual.containers import VerticalScroll
from textual.widgets import Label, Static
from craft.core.session import sessions

class HomeView(VerticalScroll):
    def compose(self):
        yield Label("[bold blue]Craft — AI 编程助手[/]", classes="panel-title")
        yield Static("欢迎回来！选择一个操作开始：", classes="status")
        yield Label("")
        yield Label("[bold]最近会话[/]")
        recent = sessions.list(5)
        if recent:
            for s in recent:
                yield Static(f"  {s['title'][:30]} ({s['message_count']}条)")
        else:
            yield Static("  (暂无会话)")
        yield Label("")
        yield Label("[bold]快捷操作[/]")
        yield Static("  /help  查看命令")
        yield Static("  /new   新建对话")
        yield Static("  /tools 查看工具")
        yield Label("")
        yield Static("[dim]Craft v0.1.0 — MiMo-Code Python Port[/]")
