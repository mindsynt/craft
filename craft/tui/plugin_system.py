"""
插件插槽 — 移植 feature-plugins/home/sidebar/system 三个插槽
通过 TuiPluginApi 与插件系统交互，提供插槽渲染、安装、切换
"""

from __future__ import annotations

from typing import Any, Callable

from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Label, ListView, ListItem, Static, Input

from craft.core.plugin import (
    PluginManager,
    Plugin,
    PluginManifest,
    plugin_manager as core_plugin_manager,
)
from craft.core.metrics import metrics


# ────────────────────────────────────────────────────────────────
# TuiPlugin API — 简化版插件 API 提供给 TUI 插件使用
# ────────────────────────────────────────────────────────────────


class TuiPluginApi:
    """TUI 插件 API 上下文"""

    def __init__(self, plugin_manager: PluginManager):
        self._pm = plugin_manager
        self._hooks: dict[str, list[Callable]] = {"command": [], "sidebar": [], "init": []}

    @property
    def plugins(self):
        return self._pm

    @property
    def metrics(self):
        return metrics

    def on(self, hook: str, handler: Callable):
        """Register a hook handler."""
        self._hooks.setdefault(hook, []).append(handler)

    def emit(self, hook: str, *args, **kwargs):
        """Emit a hook event."""
        for h in self._hooks.get(hook, []):
            h(*args, **kwargs)

    def install_plugin(self, mod: str, global_: bool = False) -> dict:
        """Install a plugin by package name."""
        try:
            result = core_plugin_manager.install_plugin(mod)
            return {"ok": True, "dir": str(result), "tui": True}
        except Exception as e:
            return {"ok": False, "message": str(e), "missing": False}

    def activate(self, plugin_id: str) -> bool:
        """Activate a plugin."""
        return core_plugin_manager.enable(plugin_id) is not None

    def deactivate(self, plugin_id: str) -> bool:
        """Deactivate a plugin."""
        return core_plugin_manager.disable(plugin_id) is not None


tui_plugin_api = TuiPluginApi(core_plugin_manager)


# ────────────────────────────────────────────────────────────────
# 插件插槽组件
# ────────────────────────────────────────────────────────────────


class HomeSlot(Vertical):
    """首页插槽 — feature-plugins/home
    显示首页插件内容：最近活动、推荐工作流等
    """

    def compose(self):
        yield Label("首页插件", classes="sidebar-title")
        # Check for home plugins
        home_plugins = [p for p in core_plugin_manager.list() if "home" in p.get("tags", [])]
        if home_plugins:
            for p in home_plugins:
                yield Static(f"  [{p.get('name', '?')}]  {p.get('description', '')[:40]}", classes="sidebar-item")
        else:
            yield Static("  (无首页插件)", classes="sidebar-item")
            yield Static("  ", classes="sidebar-item")
            # Show built-in widgets when no plugins
            try:
                summary = metrics.summary() if hasattr(metrics, 'summary') else {}
                if summary:
                    for name, count in list(summary.items())[:3]:
                        yield Static(f"  {name}: {int(count)}", classes="sidebar-item")
            except Exception:
                pass

    def on_mount(self):
        tui_plugin_api.emit("home.render", self)


class SidebarSlot(Vertical):
    """侧栏插槽 — feature-plugins/sidebar
    显示侧栏插件内容：监控、统计、快捷操作等
    """

    def compose(self):
        yield Label("侧栏插件", classes="sidebar-title")
        try:
            m = metrics.summary() if hasattr(metrics, 'summary') else {}
            if m:
                for name, count in list(m.items())[:3]:
                    yield Static(f"  {name}: {int(count)}", classes="sidebar-item")
            else:
                yield Static("  (无统计数据)", classes="sidebar-item")
        except Exception:
            yield Static("  (统计数据不可用)", classes="sidebar-item")

        yield Static("  ", classes="sidebar-item")
        # Show sidebar plugins
        sidebar_plugins = [p for p in core_plugin_manager.list() if "sidebar" in p.get("tags", [])]
        if sidebar_plugins:
            for p in sidebar_plugins:
                yield Static(f"  [{p.get('name', '?')}] {p.get('description', '')[:40]}", classes="sidebar-item")

    def on_mount(self):
        tui_plugin_api.emit("sidebar.render", self)


class SystemSlot(Vertical):
    """系统插槽 — feature-plugins/system
    显示系统插件列表、插件管理快速入口
    """

    def compose(self):
        yield Label("系统", classes="sidebar-title")
        plugins = core_plugin_manager.list()

        yield Static(f"  插件: {len(plugins)} 个", classes="sidebar-item")

        # Show plugin list with status
        if plugins:
            for p in plugins[:5]:  # Show first 5
                name = p.get("name", p.get("id", "?"))
                status = "✓" if p.get("enabled") else "○"
                yield Static(f"  {status} {name}", classes="sidebar-item")
            if len(plugins) > 5:
                yield Static(f"  ...还有 {len(plugins)-5} 个", classes="sidebar-item")
        else:
            yield Static("  (无已安装插件)", classes="sidebar-item")

    def on_mount(self):
        tui_plugin_api.emit("system.render", self)


# ────────────────────────────────────────────────────────────────
# 插件管理对话框 (移植 feature-plugins/system/plugins.tsx)
# ────────────────────────────────────────────────────────────────


from textual.screen import ModalScreen


class InstallPluginDialog(ModalScreen[str | None]):
    """安装插件对话框"""

    def __init__(self, on_install: Callable[[str, bool], None] | None = None, **kw):
        super().__init__(**kw)
        self._on_install = on_install
        self._global_scope = False

    def compose(self):
        yield Vertical(
            Label("[bold]📦 安装插件[/]", id="dlg-title"),
            Label(f"作用域: {'global' if self._global_scope else 'local'}  (Tab切换)", id="scope-label"),
            Input(placeholder="npm package name (e.g. @opencode/plugin-git)", id="pkg-input"),
            Horizontal(
                Button("安装", variant="primary", id="install-btn"),
                Button("取消", id="cancel-btn"),
            ),
            id="dialog", classes="dialog install-plugin-dialog",
        )

    def on_key(self, event):
        if event.key == "tab":
            self._global_scope = not self._global_scope
            label = self.query_one("#scope-label", Label)
            label.update(f"作用域: {'global' if self._global_scope else 'local'}  (Tab切换)")

    def on_input_submitted(self, event):
        if event.value.strip():
            if self._on_install:
                self._on_install(event.value.strip(), self._global_scope)
            self.dismiss(event.value.strip())

    def on_button_pressed(self, event):
        if event.button.id == "install-btn":
            inp = self.query_one("#pkg-input", Input).value.strip()
            if inp:
                if self._on_install:
                    self._on_install(inp, self._global_scope)
                self.dismiss(inp)
        else:
            self.dismiss(None)


class PluginManagerDialog(ModalScreen[str | None]):
    """插件管理对话框 — 列表、启用/禁用、安装"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._lock = False

    def compose(self):
        plugins = core_plugin_manager.list()
        yield Vertical(
            Label("[bold]🔌 插件管理[/]", id="dlg-title"),
            Input(placeholder="搜索插件...", id="plugin-filter"),
            ListView(
                *[ListItem(
                    Label(f"  {'✓' if p.get('enabled') else '○'} {p.get('name', p.get('id', '?'))}  {p.get('version', '')}  {''.join(p.get('tags', []))}"),
                    id=f"plg_{i}",
                ) for i, p in enumerate(plugins)],
                id="plugin-list",
            ) if plugins else Static("  (无已安装插件)", classes="sidebar-item"),
            Horizontal(
                Button("启用/禁用", id="toggle-btn"),
                Button("📦 安装", variant="primary", id="install-btn"),
                Button("关闭", id="close-btn"),
            ),
            id="dialog", classes="dialog plugin-mgr-dialog",
        )

    def on_list_view_selected(self, event):
        if event.item:
            idx = int(event.item.id.split("_")[1]) if event.item.id and event.item.id.startswith("plg_") else None
            if idx is not None:
                plugins = core_plugin_manager.list()
                if idx < len(plugins):
                    pid = plugins[idx].get("id", "")
                    self._toggle(pid)

    def on_button_pressed(self, event):
        if event.button.id == "toggle-btn":
            lst = self.query_one("#plugin-list", ListView)
            plugins = core_plugin_manager.list()
            if lst.index is not None and lst.index < len(plugins):
                self._toggle(plugins[lst.index].get("id", ""))
        elif event.button.id == "install-btn":
            self.app.push_screen(InstallPluginDialog())
            self.dismiss(None)
        elif event.button.id == "close-btn":
            self.dismiss(None)

    def _toggle(self, plugin_id: str):
        if self._lock:
            return
        self._lock = True
        try:
            plugin = core_plugin_manager.get(plugin_id)
            if plugin:
                if plugin.get("enabled"):
                    core_plugin_manager.disable(plugin_id)
                else:
                    core_plugin_manager.enable(plugin_id)
        except Exception:
            pass
        self._lock = False
        self._rebuild()

    def _rebuild(self):
        self.clear()
        self.compose()


# ─── CSS ─────────────────────────────────────────────

PLUGIN_SYSTEM_CSS = """
.install-plugin-dialog {
    width: 50;
    height: 12;
    background: #1f2335;
    border: thick #7dcfff;
}
.plugin-mgr-dialog {
    width: 60;
    height: 20;
    background: #1f2335;
    border: thick #bb9af7;
}
#scope-label {
    color: #565f89;
    padding: 0 1;
}
#plugin-list {
    height: 12;
    margin: 0 1;
}
#plugin-filter {
    margin: 0 1;
}
"""
