"""Craft TUI — 基于 OpenTUI 架构"""
from craft.tui.theme import THEMES
from craft.tui.session import SessionScreen
from craft.tui.components import DIALOG_CSS
from craft.tui.prompt import PROMPT_CSS
from textual.app import App
from textual.binding import Binding
from craft import __version__


def _build_css() -> str:
    c = THEMES["tokyo-night"].colors
    return f"""
    Screen {{ background: {c.bg}; color: {c.text}; }}
    .sidebar {{ width: 28; background: {c.sidebar}; border-right: solid {c.border}; }}
    .sidebar-title {{ color: {c.prompt}; text-style: bold; padding: 1 1 0 1; }}
    .sidebar-item {{ color: {c.text_dim}; padding: 0 1 0 2; }}
    .panel-title {{ color: {c.info}; text-style: bold; background: {c.sidebar}; padding: 0 2; }}
    .status {{ color: {c.text_dim}; }}
    .border {{ border: solid {c.border}; }}
    #chat-log {{ background: {c.surface}; color: {c.text}; padding: 1 2; }}
    #chat-input {{ background: {c.sidebar}; color: {c.text}; border: none; }}
    #input-area {{ height: 3; background: {c.sidebar}; border-top: solid {c.border}; }}
    #toolbar {{ height: 3; background: {c.sidebar}; border-bottom: solid {c.border}; }}
    ListView {{ background: {c.sidebar}; }}
    ListItem {{ color: {c.text_dim}; padding: 0 1; }}
    ListItem:hover {{ background: {c.selection}; }}
    ListItem:focus {{ background: {c.accent_bg}; color: {c.accent}; }}
    Header {{ background: {c.sidebar}; color: {c.text}; }}
    Footer {{ background: {c.sidebar}; color: {c.text_dim}; }}
    RichLog {{ background: {c.surface}; color: {c.text}; }}
    Input {{ background: {c.sidebar}; color: {c.text}; border: none; }}
    {DIALOG_CSS}
    {PROMPT_CSS}
    """


class CraftTUI(App):
    TITLE = f"Craft v{__version__}"
    SUB_TITLE = "AI 编程助手"
    CSS = _build_css()
    BINDINGS = [Binding("q", "quit", "退出", priority=True), Binding("ctrl+c", "quit", "退出", show=False)]

    def on_mount(self):
        self.push_screen(SessionScreen())


def run(theme: str = "tokyo-night"):
    app = CraftTUI()
    app.run()
