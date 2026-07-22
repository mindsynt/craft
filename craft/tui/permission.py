"""
权限请求界面 — 移植 routes/session/permission.tsx (24KB)
12+ 种权限类型的真实处理逻辑：edit, read, glob, grep, list, bash,
bash_delete, task, webfetch, websearch, codesearch, external_directory, doom_loop
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Static, TextArea

from craft.core.permission import (
    Rule, evaluate, from_config, forward_ref, FORCED_ASK,
    EDIT_TOOLS,
)


def normalize_path(input_path: str | None, cwd: str | None = None) -> str:
    """Normalize a path for display: relative to cwd, ~ for home."""
    if not input_path:
        return ""
    cwd = cwd or os.getcwd()
    home = str(Path.home())
    absolute = os.path.abspath(input_path) if not os.path.isabs(input_path) else input_path
    try:
        relative = os.path.relpath(absolute, cwd)
        if relative.startswith(".."):
            if home and (absolute == home or absolute.startswith(home + os.sep)):
                return absolute.replace(home, "~")
            return absolute
        return relative
    except ValueError:
        return absolute


PERMISSION_ICONS = {
    "edit": "→",
    "read": "→",
    "glob": "✱",
    "grep": "✱",
    "list": "→",
    "bash": "#",
    "bash_delete": "✗",
    "task": "#",
    "webfetch": "%",
    "websearch": "◈",
    "codesearch": "◇",
    "external_directory": "←",
    "doom_loop": "⟳",
}

PERMISSION_LABELS = {
    "edit": "编辑文件",
    "read": "读取文件",
    "glob": "文件通配",
    "grep": "搜索文件",
    "list": "列出目录",
    "bash": "Shell 命令",
    "bash_delete": "确认不可逆删除",
    "task": "子代理任务",
    "webfetch": "网页获取",
    "websearch": "网页搜索",
    "codesearch": "代码搜索",
    "external_directory": "访问外部目录",
    "doom_loop": "持续重试失败",
}


class PermissionPrompt(ModalScreen[bool]):
    """完整的权限审批对话框 (移植 permission.tsx)"""

    ALL_PERMISSION_TYPES = [
        "edit", "read", "glob", "grep", "list", "bash",
        "bash_delete", "task", "webfetch", "websearch",
        "codesearch", "external_directory", "doom_loop",
    ]

    def __init__(
        self,
        request_id: str = "",
        permission: str = "",
        session_id: str = "",
        tool: str = "",
        metadata: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        patterns: list[str] | None = None,
        always_patterns: list[str] | None = None,
        on_reply: Callable[[str, str | None], None] | None = None,  # reply, message
        **kw,
    ):
        super().__init__(**kw)
        self._request_id = request_id
        self._permission = permission
        self._session_id = session_id
        self._tool = tool
        self._metadata = metadata or {}
        self._data = data or {}
        self._patterns = patterns or []
        self._always_patterns = always_patterns or []
        self._on_reply = on_reply
        self._stage = "permission"  # permission, always, reject
        self._reject_message = ""

    def compose(self):
        info = self._build_info()
        options = self._get_options()

        # Permission info section
        title = info.get("title", f"工具调用: {self._permission}")
        icon = info.get("icon", "⚙")
        body_content = info.get("body", "")

        yield Vertical(
            # Header: permission title
            Label(f"[bold]{icon} {title}[/]", id="perm-title-bar"),
            # Body: permission details
            VerticalScroll(
                Static(body_content, id="perm-body", classes="perm-body"),
                id="perm-scroll",
            ),
            # Rules / always-allow info
            Label("权限选项:", classes="perm-section"),
            ListView(
                *[ListItem(Label(f"  {label}"), id=f"opt_{key}") for key, label in options.items()],
                id="perm-options",
            ),
            Horizontal(
                Button("✅ 允许一次", variant="primary", id="allow-once"),
                *([Button("🔒 总是允许", id="allow-always")] if len(options) > 2 else []),
                Button("❌ 拒绝", id="deny-btn"),
                id="perm-buttons",
            ),
            id="perm-dialog", classes="dialog perm-dialog",
        )

    def _get_options(self) -> dict[str, str]:
        """Determine visible options for this permission type."""
        if self._permission == "bash_delete":
            return {"once": "允许一次", "reject": "拒绝"}
        return {"once": "允许一次", "always": "总是允许", "reject": "拒绝"}

    def _build_info(self) -> dict[str, str]:
        """Build permission info for display (12+ permission types)."""
        p = self._permission
        data = self._data
        meta = self._metadata
        cwd = os.getcwd()

        if p == "edit":
            filepath = self._metadata.get("filepath", "")
            diff = self._metadata.get("diff", "")
            return {
                "icon": "→",
                "title": f"编辑 {normalize_path(filepath)}",
                "body": (f"路径: {normalize_path(filepath)}\n"
                        f"{'差异内容:  (见下文)' if diff else '无差异内容'}"),
            }

        if p == "read":
            from_input = data.get("file_path", "") or data.get("filePath", "")
            filepath = from_input or (self._patterns[0] if self._patterns else "")
            return {
                "icon": "→",
                "title": f"读取 {normalize_path(filepath)}",
                "body": f"路径: {normalize_path(filepath)}" if filepath else "",
            }

        if p == "glob":
            pattern = data.get("pattern", "")
            return {
                "icon": "✱",
                "title": f'通配 "{pattern}"',
                "body": f"模式: {pattern}" if pattern else "",
            }

        if p == "grep":
            pattern = data.get("pattern", "")
            return {
                "icon": "✱",
                "title": f'搜索 "{pattern}"',
                "body": f"模式: {pattern}" if pattern else "",
            }

        if p == "list":
            dir_path = data.get("path", "")
            return {
                "icon": "→",
                "title": f"列出 {normalize_path(dir_path)}",
                "body": f"路径: {normalize_path(dir_path)}" if dir_path else "",
            }

        if p == "bash":
            command = data.get("command", "")
            description = data.get("description", "") or "Shell 命令"
            return {
                "icon": "#",
                "title": description,
                "body": f"$ {command}" if command else "",
            }

        if p == "bash_delete":
            command = meta.get("command", "")
            deletes = [p for p in self._patterns if isinstance(p, str)]
            body = f"$ {command}\n" if command else ""
            if deletes:
                body += f"检测到删除:\n" + "\n".join(f"- {d}" for d in deletes)
            return {
                "icon": "✗",
                "title": "确认不可逆删除",
                "body": body,
            }

        if p == "task":
            stype = data.get("subagent_type", "未知")
            desc = data.get("description", "")
            return {
                "icon": "#",
                "title": f"{stype.title()} 任务",
                "body": f"◉ {desc}" if desc else "",
            }

        if p == "webfetch":
            url = data.get("url", "")
            return {
                "icon": "%",
                "title": f"网页获取 {url}",
                "body": f"URL: {url}" if url else "",
            }

        if p == "websearch":
            query = data.get("query", "")
            return {
                "icon": "◈",
                "title": f'网页搜索 "{query}"',
                "body": f"查询: {query}" if query else "",
            }

        if p == "codesearch":
            query = data.get("query", "")
            return {
                "icon": "◇",
                "title": f'代码搜索 "{query}"',
                "body": f"查询: {query}" if query else "",
            }

        if p == "external_directory":
            parent = meta.get("parentDir", "")
            filepath = meta.get("filepath", "")
            pattern = self._patterns[0] if self._patterns else ""
            derived = os.path.dirname(pattern) if pattern and "*" in pattern else pattern
            raw = parent or filepath or derived
            dir_name = normalize_path(raw)
            body = f"目录: {dir_name}\n"
            if self._patterns:
                body += "模式:\n" + "\n".join(f"- {p}" for p in self._patterns)
            return {
                "icon": "←",
                "title": f"访问外部目录 {dir_name}",
                "body": body,
            }

        if p == "doom_loop":
            return {
                "icon": "⟳",
                "title": "持续重试失败",
                "body": "此操作将保持会话运行而不管连续失败。",
            }

        # Fallback for unknown permission types
        return {
            "icon": "⚙",
            "title": f"调用工具 {p}",
            "body": f"工具: {p}",
        }

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item:
            key = event.item.id.split("_")[1] if event.item.id and event.item.id.startswith("opt_") else "once"
            self._handle_option(key)

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id if event.button.id else ""
        if btn_id == "allow-once":
            self._handle_option("once")
        elif btn_id == "allow-always":
            self._handle_option("always")
        elif btn_id == "deny-btn":
            self._handle_option("reject")

    def _handle_option(self, option: str):
        if option == "always":
            # Show always-allow confirmation
            self.app.push_screen(AlwaysAllowDialog(
                patterns=self._always_patterns,
                permission=self._permission,
            ), lambda result: self._on_always_done(result))
        elif option == "reject":
            # Show reject with reason dialog
            self.app.push_screen(RejectDialog(), lambda result: self._on_reject_done(result))
        else:
            # Allow once
            if self._on_reply:
                self._on_reply("once", None)
            self.dismiss(True)

    def _on_always_done(self, result: bool | None):
        if result is True:
            if self._on_reply:
                self._on_reply("always", None)
            self.dismiss(True)
        # else stay on permission screen

    def _on_reject_done(self, result: tuple[bool, str | None] | None):
        if result:
            confirmed, message = result
            if confirmed:
                if self._on_reply:
                    self._on_reply("reject", message)
                self.dismiss(False)

    def on_key(self, event):
        if event.key == "escape":
            if self._stage != "permission":
                self._stage = "permission"
                self._rebuild()
            else:
                self.dismiss(False)

    def _rebuild(self):
        """Rebuild the dialog UI (called when stage changes)."""
        self.clear()
        self.compose()


class AlwaysAllowDialog(ModalScreen[bool]):
    """总是允许确认对话框"""

    def __init__(self, patterns: list[str] | None = None, permission: str = "", **kw):
        super().__init__(**kw)
        self._patterns = patterns or []
        self._permission = permission

    def compose(self):
        if self._patterns == ["*"]:
            msg = f"这将允许 {self._permission} 直到 Craft 重启。"
        else:
            msg = "这将允许以下模式直到 Craft 重启：\n" + "\n".join(f"- {p}" for p in self._patterns)
        yield Vertical(
            Label("[bold]🔒 总是允许确认[/]", id="dlg-title"),
            Static(msg, id="always-msg"),
            Horizontal(
                Button("取消", id="cancel-btn"),
                Button("确认", variant="primary", id="confirm-btn"),
            ),
            id="dialog", classes="dialog always-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)


class RejectDialog(ModalScreen[tuple[bool, str | None]]):
    """拒绝原因对话框"""

    def compose(self):
        yield Vertical(
            Label("[bold]❌ 拒绝权限[/]", id="dlg-title"),
            Static("告诉 AI 应该怎么做："),
            Input(placeholder="输入反馈信息（可选）...", id="reject-input"),
            Horizontal(
                Button("取消", id="cancel-btn"),
                Button("确认拒绝", variant="primary", id="confirm-btn"),
            ),
            id="dialog", classes="dialog reject-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "confirm-btn":
            msg = self.query_one("#reject-input", Input).value
            self.dismiss((True, msg.strip() or None))
        else:
            self.dismiss((False, None))


class PermissionPanel(Vertical):
    """权限状态显示面板 — 显示待审批的工具调用"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._pending: list[dict] = []
        self._status = Static("  无待审批", classes="sidebar-item", id="perm-status")

    def compose(self):
        yield Label("权限", classes="sidebar-title")
        yield self._status

    def add_request(self, tool: str, agent: str, permission: str = ""):
        self._pending.append({"tool": tool, "agent": agent, "permission": permission})
        self._update()

    def resolve(self, tool: str | None = None):
        if tool:
            self._pending = [p for p in self._pending if p["tool"] != tool]
        else:
            self._pending.pop(0) if self._pending else None
        self._update()

    def _update(self):
        if self._pending:
            self._status.update(f"  ⏳ {len(self._pending)} 个待审批")
        else:
            self._status.update("  无待审批")


# ────────────────────────────────────────────────────────────────
# 权限规则评估工具 (移植 permission.tsx 的 evaluate + normalize)
# ────────────────────────────────────────────────────────────────


def format_permission_info(permission: str, data: dict[str, Any], metadata: dict[str, Any],
                          patterns: list[str] | None = None) -> dict[str, str]:
    """Format permission info for display (standalone helper)."""
    if permission == "edit":
        filepath = metadata.get("filepath", "")
        diff = metadata.get("diff", "")
        return {
            "icon": "→",
            "title": f"编辑 {normalize_path(filepath)}",
            "has_diff": bool(diff),
        }
    if permission == "bash":
        command = data.get("command", "")
        description = data.get("description", "") or "Shell 命令"
        return {"icon": "#", "title": description, "command": command}
    if permission == "webfetch":
        url = data.get("url", "")
        return {"icon": "%", "title": f"网页获取 {url}", "url": url}
    if permission == "websearch":
        query = data.get("query", "")
        return {"icon": "◈", "title": f'网页搜索 "{query}"', "query": query}
    if permission == "read":
        filepath = data.get("file_path", "") or data.get("filePath", "")
        return {"icon": "→", "title": f"读取 {normalize_path(filepath)}"}
    if permission == "bash_delete":
        command = metadata.get("command", "")
        deletes = [p for p in (patterns or []) if isinstance(p, str)]
        return {"icon": "✗", "title": "确认不可逆删除", "command": command, "deletes": deletes}
    if permission == "task":
        stype = data.get("subagent_type", "未知")
        desc = data.get("description", "")
        return {"icon": "#", "title": f"{stype.title()} 任务", "description": desc}
    if permission == "glob":
        pattern = data.get("pattern", "")
        return {"icon": "✱", "title": f'通配 "{pattern}"'}
    if permission == "grep":
        pattern = data.get("pattern", "")
        return {"icon": "✱", "title": f'搜索 "{pattern}"'}
    if permission == "list":
        path = data.get("path", "")
        return {"icon": "→", "title": f"列出 {normalize_path(path)}"}
    if permission == "codesearch":
        query = data.get("query", "")
        return {"icon": "◇", "title": f'代码搜索 "{query}"'}
    if permission == "external_directory":
        meta = metadata
        parent = meta.get("parentDir", "")
        filepath = meta.get("filepath", "")
        pattern = patterns[0] if patterns else ""
        derived = os.path.dirname(pattern) if pattern and "*" in pattern else pattern
        raw = parent or filepath or derived
        return {"icon": "←", "title": f"访问外部目录 {normalize_path(raw)}"}
    if permission == "doom_loop":
        return {"icon": "⟳", "title": "持续重试失败"}
    return {"icon": "⚙", "title": f"调用工具 {permission}"}


# ─── CSS ─────────────────────────────────────────────

PERMISSION_CSS = """
.perm-dialog {
    width: 60;
    height: 22;
    background: #1f2335;
    border: thick #e0af68;
}
#perm-title-bar {
    padding: 0 1 1 1;
    color: #e0af68;
    text-style: bold;
}
#perm-body {
    padding: 0 1;
    color: #c0caf5;
}
#perm-scroll {
    height: 8;
}
.perm-section {
    padding: 1 1 0 1;
    color: #73daca;
    text-style: bold;
}
.perm-body {
    color: #c0caf5;
}
#perm-options {
    height: 5;
    margin: 0 1;
}
#perm-buttons {
    height: 3;
    align: center middle;
    padding: 0 1;
}
.always-dialog {
    width: 50;
    height: 12;
    background: #1f2335;
    border: thick #7dcfff;
}
#always-msg {
    padding: 1 1;
    color: #c0caf5;
}
.reject-dialog {
    width: 50;
    height: 10;
    background: #1f2335;
    border: thick #f7768e;
}
#reject-input {
    margin: 1;
}
"""
