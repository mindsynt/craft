"""
对话系列 — 移植 component/dialog-* 系列
Provider配置、模型选择、MCP管理、命令面板、暂存
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, ListView, ListItem, Select


class ProviderDialog(ModalScreen[dict | None]):
    """提供商配置对话框 (移植 dialog-provider.tsx)"""
    def __init__(self, **kw):
        super().__init__(**kw)

    def compose(self):
        yield Vertical(
            Label("[bold]🔌 提供商配置[/]", id="dlg-title"),
            Label("提供商:"), Select([("OpenAI","openai"),("Anthropic","anthropic"),("Ollama","ollama")], id="sel-provider"),
            Label("API Key:"), Input(placeholder="sk-...", id="inp-key", password=True),
            Label("Base URL:"), Input(placeholder="https://api.openai.com/v1", id="inp-url"),
            Horizontal(
                Button("✅ 保存", variant="primary", id="save-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save-btn":
            self.dismiss({
                "provider": self.query_one("#sel-provider", Select).value,
                "api_key": self.query_one("#inp-key", Input).value,
                "base_url": self.query_one("#inp-url", Input).value,
            })
        else:
            self.dismiss(None)


class ModelDialog(ModalScreen[str | None]):
    """模型选择对话框 (移植 dialog-model.tsx)"""
    def __init__(self, models: list[str] | None = None, **kw):
        super().__init__(**kw)
        self._models = models or ["gpt-4o","gpt-4o-mini","claude-sonnet-4","llama3"]

    def compose(self):
        yield Vertical(
            Label("[bold]🤖 选择模型[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {m}")) for m in self._models], id="model-list"),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog model-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            label = str(event.item.children[0].renderable) if event.item.children else ""
            self.dismiss(label.strip())

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


class CommandPalette(ModalScreen[str | None]):
    """命令面板 (移植 dialog-command.tsx)"""
    def __init__(self, **kw):
        super().__init__(**kw)

    def compose(self):
        yield Vertical(
            Label("[bold]⌨️ 命令面板[/]", id="dlg-title"),
            Input(placeholder="输入命令...", id="cmd-input"),
            ListView(
                ListItem(Label("  /help    查看帮助")),
                ListItem(Label("  /new     新建对话")),
                ListItem(Label("  /tools   工具列表")),
                ListItem(Label("  /clear   清屏")),
                ListItem(Label("  /exit    退出")),
                id="cmd-list",
            ),
            id="dialog", classes="dialog cmd-dialog",
        )

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            self.dismiss(str(event.item.children[0].renderable).split()[0].strip())


class StashDialog(ModalScreen[str | None]):
    """暂存管理 (移植 dialog-stash.tsx)"""
    def __init__(self, stashes: list[str] | None = None, **kw):
        super().__init__(**kw)
        self._stashes = stashes or []

    def compose(self):
        items = self._stashes or ["(无暂存内容)"]
        yield Vertical(
            Label("[bold]📦 暂存管理[/]", id="dlg-title"),
            ListView(*[ListItem(Label(f"  {s[:50]}")) for s in items], id="stash-list"),
            Horizontal(
                Button("恢复", variant="primary", id="restore-btn"),
                Button("删除", id="delete-btn"),
                Button("关闭", id="close-btn"),
            ),
            id="dialog", classes="dialog",
        )


DIALOGS_CSS = """
.model-dialog { height: 16; }
.cmd-dialog { height: 14; }
#model-list { height: 10; }
#cmd-list { height: 8; }
#cmd-input { margin: 0; }
"""
