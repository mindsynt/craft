"""
会话子组件 — 移植 routes/session/dialog-* 系列
含：时间线、分支、消息操作、子代理
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Static, TextArea

from craft.core.session import sessions, Session


class SessionListDialog(ModalScreen[str | None]):
    """会话列表 (移植 component/dialog-session-list.tsx)"""

    def __init__(self, session_list: list[dict] | None = None, current_id: str | None = None,
                 on_delete: callable | None = None, on_rename: callable | None = None,
                 on_select: callable | None = None, **kw):
        super().__init__(**kw)
        self._sessions = session_list or []
        self._current_id = current_id
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_select = on_select
        self._to_delete: str | None = None

    def compose(self):
        yield Vertical(
            Label("[bold]📋 会话列表[/]", id="dlg-title"),
            Input(placeholder="搜索会话...", id="session-filter"),
            ListView(
                *[ListItem(Label(f"  {'↳ ' if s.get('parentID') else ''}{'●' if s.get('id')==self._current_id else '○'} {s.get('title','?')[:40]}  [{s.get('message_count',0)}条]"), id=f"ses_{i}") for i, s in enumerate(self._sessions)],
                id="session-list-view",
            ),
            Horizontal(
                Button("打开", variant="primary", id="open-btn"),
                Button("重命名", id="rename-btn"),
                Button("删除", id="delete-btn"),
                Button("关闭", id="close-btn"),
            ),
            id="dialog", classes="dialog session-list-dialog",
        )

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            idx = int(event.item.id.split("_")[1])
            if 0 <= idx < len(self._sessions):
                session_id = self._sessions[idx].get("id", "")
                if self._on_select:
                    self._on_select(session_id)
                self.dismiss(session_id)

    def on_button_pressed(self, event: Button.Pressed):
        lst = self.query_one("#session-list-view", ListView)
        if lst.index is not None and 0 <= lst.index < len(self._sessions):
            session_id = self._sessions[lst.index].get("id", "")
            if event.button.id == "open-btn":
                if self._on_select:
                    self._on_select(session_id)
                self.dismiss(session_id)
            elif event.button.id == "rename-btn":
                if self._on_rename:
                    self._on_rename(session_id)
                self.dismiss("__rename__")
            elif event.button.id == "delete-btn":
                if self._on_delete:
                    self._on_delete(session_id)
                self.dismiss("__delete__")
        if event.button.id == "close-btn":
            self.dismiss(None)


class ForkDialog(ModalScreen[dict | None]):
    """会话分支 (移植 dialog-fork-from-timeline.tsx)"""

    def __init__(self, session_id: str = "", **kw):
        super().__init__(**kw)
        self._session_id = session_id

    def compose(self):
        yield Vertical(
            Label("[bold]🔀 创建分支会话[/]", id="dlg-title"),
            Static("从当前会话创建新分支:"),
            Input(value="分支: 新方案", id="fork-name"),
            Static(""),
            Static("选择分支起点:"),
            ListView(
                ListItem(Label("  📄 完整会话")),
                ListItem(Label("  📝 从第一条用户消息")),
                ListItem(Label("  📌 从当前消息")),
                id="fork-point",
            ),
            Horizontal(
                Button("创建分支", variant="primary", id="fork-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog fork-dialog",
        )

    def on_button_pressed(self, event):
        if event.button.id == "fork-btn":
            name = self.query_one("#fork-name", Input).value
            point = self.query_one("#fork-point", ListView).index
            self.dismiss({"name": name, "point_index": point})
        else:
            self.dismiss(None)


class MessageDialog(ModalScreen[dict | None]):
    """消息操作 (移植 dialog-message.tsx)"""

    def __init__(self, role: str = "", content: str = "",
                 message_id: str = "", session_id: str = "",
                 on_revert: callable | None = None, on_fork: callable | None = None,
                 on_copy: callable | None = None, **kw):
        super().__init__(**kw)
        self._role = role
        self._content = content
        self._message_id = message_id
        self._session_id = session_id
        self._on_revert = on_revert
        self._on_fork = on_fork
        self._on_copy = on_copy

    def compose(self):
        yield Vertical(
            Label(f"[bold]{'🤖 ' if self._role=='assistant' else '📝 '}消息操作[/]", id="dlg-title"),
            Static(f"[dim]{self._role}[/]"),
            Static(self._content[:200], id="msg-preview"),
            ListView(
                ListItem(Label("  ↩️ 回退 — 撤销消息及文件更改")),
                ListItem(Label("  📋 复制 — 将消息文本复制到剪贴板")),
                ListItem(Label("  🔀 分支 — 从此消息创建新会话")),
                id="msg-actions",
            ),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog msg-dialog",
        )

    def on_list_view_selected(self, event):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx == 0 and self._on_revert:
                self._on_revert(self._message_id, self._session_id)
                self.dismiss({"action": "revert"})
            elif idx == 1 and self._on_copy:
                self._on_copy(self._content)
                self.dismiss({"action": "copy"})
            elif idx == 2 and self._on_fork:
                self._on_fork(self._message_id, self._session_id)
                self.dismiss({"action": "fork"})

    def on_button_pressed(self, event):
        self.dismiss()


class TimelineDialog(ModalScreen[str | None]):
    """会话时间线 (移植 routes/session/dialog-timeline.tsx)"""

    def __init__(self, messages: list[dict] | None = None, session_id: str = "", **kw):
        super().__init__(**kw)
        self._messages = messages or []
        self._session_id = session_id

    def compose(self):
        yield Vertical(
            Label("[bold]📋 会话时间线[/]", id="dlg-title"),
            ListView(
                *[ListItem(Label(f"  {'📝' if m.get('role')=='user' else '🤖'} 用户: {m.get('content','')[:50]}"), id=f"msg_{i}") for i, m in enumerate(self._messages) if m.get('role') == 'user'],
                id="timeline-list",
            ),
            Button("关闭", id="close-btn"),
            id="dialog", classes="dialog timeline-dialog",
        )

    def on_list_view_selected(self, event):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("msg_") else None
            if idx is not None and idx < len(self._messages):
                self.dismiss(self._messages[idx].get("id", ""))

    def on_button_pressed(self, event):
        self.dismiss(None)


class SubagentDialog(ModalScreen[dict | None]):
    """子代理管理 (移植 routes/session/dialog-subagent.tsx)"""

    def __init__(self, subagents: list[dict] | None = None, **kw):
        super().__init__(**kw)
        self._subagents = subagents or []

    def compose(self):
        items = [ListItem(Label(f"  {a.get('actor_id','?')}  {a.get('agent','')}  [{a.get('status','')}]")) for a in self._subagents]
        yield Vertical(
            Label("[bold]🔀 子代理管理[/]", id="dlg-title"),
            ListView(*items, id="subagent-list") if items else Static("  (此会话无子代理)"),
            Horizontal(
                Button("查看", variant="primary", id="view-btn"),
                Button("关闭", id="close-btn"),
            ),
            id="dialog", classes="dialog subagent-dialog",
        )

    def on_list_view_selected(self, event):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("opt_") else None
            if idx is not None and idx < len(self._subagents):
                self.dismiss(self._subagents[idx])

    def on_button_pressed(self, event):
        if event.button.id == "view-btn":
            lst = self.query_one("#subagent-list", ListView)
            if lst.index is not None and lst.index < len(self._subagents):
                self.dismiss(self._subagents[lst.index])
        elif event.button.id == "close-btn":
            self.dismiss(None)


class SessionRenameDialog(ModalScreen[str | None]):
    """重命名会话 (移植 component/dialog-session-rename.tsx)"""

    def __init__(self, session_title: str = "", on_rename: callable | None = None, **kw):
        super().__init__(**kw)
        self._title = session_title
        self._on_rename = on_rename

    def compose(self):
        yield Vertical(
            Label("[bold]✏️ 重命名会话[/]", id="dlg-title"),
            Input(value=self._title, placeholder="输入新名称...", id="rename-input"),
            Horizontal(
                Button("确认", variant="primary", id="confirm-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog rename-dialog",
        )

    def on_input_submitted(self, event):
        if self._on_rename:
            self._on_rename(event.value)
        self.dismiss(event.value)

    def on_button_pressed(self, event):
        if event.button.id == "confirm-btn":
            val = self.query_one("#rename-input", Input).value
            if self._on_rename:
                self._on_rename(val)
            self.dismiss(val)
        else:
            self.dismiss(None)


class ForkFromTimelineDialog(ModalScreen[dict | None]):
    """从时间线分支 (移植 routes/session/dialog-fork-from-timeline.tsx)"""

    def __init__(self, messages: list[dict] | None = None, session_id: str = "",
                 on_fork: callable | None = None, **kw):
        super().__init__(**kw)
        self._messages = messages or []
        self._session_id = session_id
        self._on_fork = on_fork

    def compose(self):
        yield Vertical(
            Label("[bold]🔀 分支会话 — 选择起点[/]", id="dlg-title"),
            ListView(
                ListItem(Label("  📄 完整会话"), id="fork_full"),
                *[ListItem(Label(f"  📝 {m.get('content','')[:50]}"), id=f"fork_{i}") for i, m in enumerate(self._messages) if m.get('role') == 'user'],
                id="fork-list",
            ),
            Button("取消", id="cancel-btn"),
            id="dialog", classes="dialog fork-timeline-dialog",
        )

    def on_list_view_selected(self, event):
        if event.item:
            if event.item.id == "fork_full":
                if self._on_fork:
                    self._on_fork(self._session_id, None)
                self.dismiss({"session_id": self._session_id, "message_id": None})
            elif event.item.id.startswith("fork_"):
                idx = int(event.item.id.split("_")[1])
                user_msgs = [m for m in self._messages if m.get('role') == 'user']
                if idx < len(user_msgs):
                    mid = user_msgs[idx].get("id", "")
                    if self._on_fork:
                        self._on_fork(self._session_id, mid)
                    self.dismiss({"session_id": self._session_id, "message_id": mid})

    def on_button_pressed(self, event):
        self.dismiss(None)


class FooterWidget(Horizontal):
    """会话页脚 (移植 routes/session/footer.tsx)"""

    def __init__(self, agent: str = "build", model: str = "gpt-4o", msg_count: int = 0, **kw):
        super().__init__(**kw)
        self._agent = agent
        self._model = model
        self._msg_count = msg_count

    def compose(self):
        yield Label(f"  Agent: [yellow]{self._agent}[/]")
        yield Label(f"  模型: [green]{self._model}[/]")
        yield Label(f"  消息: [cyan]{self._msg_count}[/]")
        yield Label("  Tab补全  ↑↓历史  /help命令", classes="status")

    def update_info(self, agent: str = "", model: str = "", msg_count: int = 0):
        if agent:
            self._agent = agent
        if model:
            self._model = model
        if msg_count is not None:
            self._msg_count = msg_count
        self.remove_children()
        self.compose()


SESSION_DIALOGS_CSS = """
.session-list-dialog { height: 20; }
.fork-dialog { height: 16; }
.msg-dialog { height: 14; }
.timeline-dialog { height: 16; }
.subagent-dialog { height: 14; }
.rename-dialog { height: 8; }
.fork-timeline-dialog { height: 16; }
#session-list-view { height: 12; }
#timeline-list { height: 10; }
#subagent-list { height: 8; }
#msg-preview { padding: 0 1; color: #565f89; max-height: 5; }
#fork-list { height: 10; }
#fork-point { height: 5; }
#msg-actions { height: 5; }
"""
