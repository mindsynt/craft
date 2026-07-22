"""
Craft TUI — 精简可用的版本
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static, ListView, ListItem
from craft import __version__


class ChatScreen(Vertical):
    def compose(self):
        yield Static("[bold blue]Craft v{} — AI 编程助手[/]".format(__version__), id="title")
        self._log = RichLog(highlight=True, markup=True, wrap=True, id="chat")
        yield self._log
        self._input = Input(placeholder="输入消息... (Enter发送  /help查看命令)", id="input")
        yield self._input

    def on_mount(self):
        self._log.write("欢迎使用 Craft AI 编程助手！")
        self._log.write("输入 /help 查看命令")

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return
        self._log.write(f"[bold green]你[/]: {text}")
        self._input.value = ""

        if text.startswith("/help"):
            self._log.write("[bold yellow]命令列表[/]:")
            self._log.write("  /help   查看帮助")
            self._log.write("  /agent  切换Agent")
            self._log.write("  /model  切换模型")
            self._log.write("  /clear  清屏")
            self._log.write("  /exit   退出")
        elif text.startswith("/clear"):
            self._log.clear()
        elif text.startswith("/exit"):
            self.app.exit()
        else:
            self._log.write(f"[dim]Craft[/]: 收到消息（需要配置 API Key 才能回复）")


class CraftTUI(App):
    TITLE = f"Craft v{__version__}"
    CSS = """
    Screen { background: #1a1b26; color: #c0caf5; }
    #title { padding: 0 2; text-style: bold; background: #1f2335; border-bottom: solid #2f3340; }
    #chat { padding: 1 2; background: #1a1b26; }
    #input { background: #1f2335; color: #c0caf5; border: none; margin: 0 2; }
    ListView { background: #1f2335; }
    ListItem { color: #c0caf5; }
    """

    def compose(self):
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar", classes="box"):
                yield Static("[bold]Agent[/]", classes="sidebar-title")
                yield ListView(ListItem(Static("  Build")), ListItem(Static("  Plan")), id="agent-list")
                yield Static("[bold]会话[/]", classes="sidebar-title")
                yield Static("  新建对话", classes="sidebar-item")
            yield ChatScreen(id="main")
        yield Footer()

    def on_mount(self):
        self.screen.query_one("#input", Input).focus()


def run():
    CraftTUI().run()
