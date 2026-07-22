"""
权限请求界面 — 移植 routes/session/permission.tsx (24KB)
工具调用权限审批、规则显示、一键授权
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, ListView, ListItem


class PermissionRequest(ModalScreen[bool]):
    """权限审批对话框"""

    def __init__(self, tool_name: str, agent_id: str = "build",
                 args: dict | None = None, rule: str = "", **kw):
        super().__init__(**kw)
        self._tool = tool_name
        self._agent = agent_id
        self._args = args or {}
        self._rule = rule

    def compose(self):
        yield Vertical(
            Label("[bold]🔒 工具调用权限请求[/]", id="perm-title"),
            Static(f"[yellow]Agent: {self._agent}[/]", classes="perm-item"),
            Static(f"[cyan]工具: {self._tool}[/]", classes="perm-item"),
            Static(f"[dim]参数: {str(self._args)[:80]}[/]", classes="perm-item"),
            Label("权限规则:", classes="perm-section"),
            ListView(
                ListItem(Label(f"  {r}") for r in [
                    f"允许 {self._tool}",
                    "单次授权",
                    "会话内授权",
                    "始终允许",
                ]),
                id="perm-rules",
            ),
            Horizontal(
                Button("✅ 允许一次", variant="primary", id="allow-once"),
                Button("📌 会话内允许", id="allow-session"),
                Button("🔒 始终允许", id="allow-always"),
                Button("❌ 拒绝", id="deny-btn"),
                id="perm-buttons",
            ),
            id="perm-dialog", classes="dialog perm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "deny-btn":
            self.dismiss(False)
        else:
            self.dismiss(True)


class PermissionPanel(Vertical):
    """权限状态显示面板"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._pending: list[dict] = []

    def compose(self):
        yield Label("权限", classes="sidebar-title")
        self._status = Static("  无待审批", classes="sidebar-item")
        yield self._status

    def add_request(self, tool: str, agent: str):
        self._pending.append({"tool": tool, "agent": agent})
        self._update()

    def resolve(self, tool: str):
        self._pending = [p for p in self._pending if p["tool"] != tool]
        self._update()

    def _update(self):
        if self._pending:
            self._status.update(f"  ⏳ {len(self._pending)} 个待审批")
        else:
            self._status.update("  无待审批")


# ─── CSS ─────────────────────────────────────────────
PERMISSION_CSS = """
.perm-dialog {
    width: 50;
    height: 20;
    background: #1f2335;
    border: thick #e0af68;
}
#perm-title {
    padding: 0 1 1 1;
    color: #e0af68;
}
.perm-item {
    padding: 0 1;
    color: #c0caf5;
}
.perm-section {
    padding: 1 1 0 1;
    color: #73daca;
    text-style: bold;
}
#perm-rules {
    height: 6;
    margin: 0 1;
}
#perm-buttons {
    height: 3;
    align: center middle;
    padding: 0 1;
}
"""
