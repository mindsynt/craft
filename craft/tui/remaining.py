"""
剩余组件汇总 — 移植 ui/home/, routes/session/dialog*, routes/home.tsx, config/
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, ListView, ListItem, Select, TextArea


# ─── 首页提示 (移植 ui/home/tips.tsx + tips-view.tsx) ─
class TipsWidget(Vertical):
    def compose(self):
        yield Label("提示", classes="sidebar-title")
        tips = [
            "Tab 键自动补全命令",
            "↑↓ 键浏览输入历史",
            "/help 查看全部命令",
            "/diff 查看代码变更",
            "/memory add 保存重要信息",
        ]
        for t in tips:
            yield Static(f"  {t}", classes="sidebar-item")


# ─── 问题面板 (移植 routes/session/question.tsx, 16KB) ──
class QuestionPanel(Vertical):
    def compose(self):
        yield Label("问题", classes="sidebar-title")
        self._question = Static("  等待提问...", classes="sidebar-item")
        self._answer = Static("", classes="sidebar-item")
        yield self._question
        yield self._answer

    def show(self, question: str):
        self._question.update(f"[yellow]❓ {question}[/]")

    def answer(self, text: str):
        self._answer.update(f"[green]  {text}[/]")


# ─── 时间线对话框 (移植 routes/session/dialog-timeline.tsx) ─
class TimelineDialog(ModalScreen):
    def compose(self):
        yield Vertical(
            Label("[bold]📋 会话时间线[/]"),
            ListView(
                ListItem(Label("  📝 用户: 如何优化查询？")),
                ListItem(Label("  🤖 助手: 建议加索引")),
                ListItem(Label("  📝 用户: 具体方案？")),
                ListItem(Label("  🤖 助手: 1.分析慢查询 2.索引")),
                id="timeline-list",
            ),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog",
        )
    def on_button_pressed(self, event): self.dismiss()


# ─── 子代理对话框 (移植 routes/session/dialog-subagent.tsx) ─
class SubagentDialog(ModalScreen[dict | None]):
    def compose(self):
        yield Vertical(
            Label("[bold]🔀 子代理管理[/]"),
            Label("选择子代理:"),
            Select([("Build 开发者","build"),("Plan 分析师","plan"),("Explore 研究员","explore")], id="sel-subagent"),
            Label("任务描述:"),
            TextArea("", id="subagent-task"),
            Horizontal(
                Button("执行", variant="primary", id="run-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog",
        )
    def on_button_pressed(self, event):
        if event.button.id == "run-btn":
            self.dismiss({"agent": self.query_one("#sel-subagent", Select).value,
                          "task": self.query_one("#subagent-task", TextArea).text})
        else:
            self.dismiss(None)


# ─── 会话列表对话框 (移植 component/dialog-session-list.tsx) ─
class SessionListDialog(ModalScreen[str | None]):
    def compose(self):
        from craft.core.session import sessions
        items = [ListItem(Label(f"  {s['title'][:30]} ({s['message_count']}条)")) for s in sessions.list(20)]
        yield Vertical(
            Label("[bold]📋 会话列表[/]"),
            ListView(*items, id="session-list-view"),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog",
        )
    def on_list_view_selected(self, event):
        pass
    def on_button_pressed(self, event):
        self.dismiss(None)


# ─── TUI 配置面板 (移植 config/tui.ts) ──
class TUIConfigPanel(VerticalScroll):
    def compose(self):
        yield Label("[bold]TUI 配置[/]", classes="panel-title")
        yield Label("主题:")
        yield Select([(t, t) for t in ["tokyo-night","dracula","monokai","light"]], value="tokyo-night", id="sel-theme")
        yield Label("语言:")
        yield Select([("中文","zh"),("English","en")], value="zh", id="sel-lang")
        yield Label("侧栏宽度:")
        yield Select([("窄 (20)","20"),("中 (28)","28"),("宽 (36)","36")], value="28", id="sel-sidebar")
        yield Static("  Craft v0.1.0 — MiMo-Code Python Port", classes="sidebar-item")


# ─── 插件管理面板 (移植 ui/system/plugins.tsx) ──
class PluginPanel(VerticalScroll):
    def compose(self):
        yield Label("[bold]插件管理[/]", classes="panel-title")
        from craft.core.plugin import plugin_manager
        plugins = plugin_manager.list()
        if plugins:
            for p in plugins:
                yield Static(f"  [cyan]{p['name']}[/] v{p['version']}")
                yield Static(f"    {p['description']}")
        else:
            yield Static("  (无已安装插件)", classes="sidebar-item")


REMAINING_CSS = """
#timeline-list { height: 10; }
#session-list-view { height: 12; }
#subagent-task { height: 5; }
"""
