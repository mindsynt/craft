"""
UI 组件 — 移植自 OpenTUI ui/ + component/ 系列
对话框、Toast、Spinner、自动补全、提示
"""

from __future__ import annotations

import asyncio
import itertools

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, RichLog, Static


# ─── Spinner 加载指示器 ──────────────────────────────
class Spinner(Static):
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str = "处理中...", **kw):
        super().__init__(text, **kw)
        self._text = text
        self._running = False

    def on_mount(self):
        self.start()

    def start(self):
        self._running = True
        self._spin()

    async def _spin(self):
        spinner = itertools.cycle(self.FRAMES)
        while self._running:
            try:
                self.update(f"[bold cyan]{next(spinner)}[/] {self._text}")
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break

    def stop(self):
        self._running = False
        self.update("")


# ─── Toast 通知 ──────────────────────────────────────
class Toast(RichLog):
    def __init__(self, **kw):
        super().__init__(max_lines=3, highlight=True, markup=True, **kw)

    def show(self, message: str, type: str = "info"):
        icons = {"info": "[blue]ℹ[/]", "success": "[green]✓[/]",
                 "warning": "[yellow]⚠[/]", "error": "[red]✗[/]"}
        icon = icons.get(type, "[blue]ℹ[/]")
        self.write(f"{icon} {message}")


# ─── 确认对话框 ──────────────────────────────────────
class ConfirmDialog(ModalScreen[bool]):
    def __init__(self, title: str, message: str, **kw):
        super().__init__(**kw)
        self.dlg_title = title
        self.dlg_message = message

    def compose(self):
        yield Vertical(
            Label(f"[bold]{self.dlg_title}[/]", id="dlg-title"),
            Static(self.dlg_message, id="dlg-msg"),
            Horizontal(
                Button("确认", variant="primary", id="confirm-btn"),
                Button("取消", id="cancel-btn"),
                id="dlg-buttons",
            ),
            id="dialog",
            classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)


# ─── 提示对话框 ──────────────────────────────────────
class PromptDialog(ModalScreen[str | None]):
    def __init__(self, title: str, prompt: str, default: str = "", **kw):
        super().__init__(**kw)
        self.dlg_title = title
        self.dlg_prompt = prompt
        self.default = default

    def compose(self):
        yield Vertical(
            Label(f"[bold]{self.dlg_title}[/]"),
            Label(self.dlg_prompt),
            Input(value=self.default, id="prompt-input"),
            Horizontal(
                Button("确认", variant="primary", id="ok-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "ok-btn":
            self.dismiss(self.query_one("#prompt-input", Input).value)
        else:
            self.dismiss(None)


# ─── 选择对话框 ──────────────────────────────────────
class SelectDialog(ModalScreen[str | None]):
    def __init__(self, title: str, items: list[str], **kw):
        super().__init__(**kw)
        self.dlg_title = title
        self.items = items

    def compose(self):
        yield Vertical(
            Label(f"[bold]{self.dlg_title}[/]"),
            ListView(*[ListItem(Label(i)) for i in self.items], id="select-list"),
            Horizontal(Button("取消", id="cancel-btn"), id="dlg-buttons"),
            id="dialog", classes="dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        self.dismiss(str(event.item.label.renderable) if event.item else None)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)


# ─── 消息对话框 ──────────────────────────────────────
class AlertDialog(ModalScreen):
    def __init__(self, title: str, message: str, **kw):
        super().__init__(**kw)
        self.dlg_title = title
        self.dlg_message = message

    def compose(self):
        yield Vertical(
            Label(f"[bold]{self.dlg_title}[/]"),
            Static(self.dlg_message),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss()


# ─── 对话框 CSS ──────────────────────────────────────
DIALOG_CSS = """
.dialog {
    width: 40;
    height: auto;
    padding: 1 2;
    background: #1f2335;
    border: thick #7aa2f7;
    margin: 4 8;
}
#dlg-title {
    text-style: bold;
    color: #7dcfff;
    padding-bottom: 1;
}
#dlg-msg {
    color: #c0caf5;
    padding-bottom: 1;
}
#dlg-buttons {
    height: 3;
    align: center middle;
}
#prompt-input {
    margin: 1 0;
}
#select-list {
    height: 10;
}
"""
