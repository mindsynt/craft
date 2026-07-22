"""
会话子组件 — 移植 remaining routes/session/dialog-* 
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, ListView, ListItem


class ForkDialog(ModalScreen[dict | None]):
    """会话分支 (移植 dialog-fork-from-timeline.tsx)"""
    def compose(self):
        yield Vertical(
            Label("[bold]🔀 创建分支会话[/]"),
            Label("从当前会话创建新分支:"),
            Input(value="分支: 新方案", id="fork-name"),
            Horizontal(
                Button("创建分支", variant="primary", id="fork-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog",
        )
    def on_button_pressed(self, event):
        if event.button.id == "fork-btn":
            self.dismiss({"name": self.query_one("#fork-name", Input).value})
        else:
            self.dismiss(None)


class MessageDialog(ModalScreen[dict | None]):
    """消息详情 (移植 dialog-message.tsx)"""
    def __init__(self, role: str = "", content: str = "", **kw):
        super().__init__(**kw)
        self._role = role
        self._content = content
    def compose(self):
        yield Vertical(
            Label(f"[bold]{'🤖 ' if self._role=='assistant' else '📝 '}消息详情[/]"),
            Static(f"[dim]{self._role}[/]"),
            Static(self._content[:500]),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog",
        )
    def on_button_pressed(self, event): self.dismiss()


class FooterWidget(Horizontal):
    """会话页脚 (移植 routes/session/footer.tsx)"""
    def compose(self):
        yield Label(f"  Agent: [yellow]build[/]")
        yield Label(f"  模型: [green]gpt-4o[/]")
        yield Label(f"  消息: [cyan]0[/]")
        yield Label(f"  Tab补全  ↑↓历史  /help命令", classes="status")
