"""
插件插槽 — 移植 plugin/ 系列
feature-plugins: home/sidebar/system 三个插槽
"""

from __future__ import annotations

from typing import Any, Callable

from textual.containers import Vertical
from textual.widgets import Button, Label, Static
from craft.core.plugin import plugin_manager


class PluginSlot:
    """插件插槽基类"""
    def __init__(self, name: str):
        self.name = name

    def render(self, parent):
        """渲染插槽内容"""
        pass


class HomeSlot(Vertical):
    """首页插槽 — feature-plugins/home"""
    def compose(self):
        yield Label("首页插件", classes="sidebar-title")


class SidebarSlot(Vertical):
    """侧栏插槽 — feature-plugins/sidebar"""
    def compose(self):
        yield Label("侧栏插件", classes="sidebar-title")
        from craft.core.metrics import metrics
        m = metrics.summary()
        if m:
            for name, count in list(m.items())[:3]:
                yield Static(f"  {name}: {int(count)}", classes="sidebar-item")


class SystemSlot(Vertical):
    """系统插槽 — feature-plugins/system"""
    def compose(self):
        yield Label("系统", classes="sidebar-title")
        plugins = plugin_manager.list()
        yield Static(f"  插件: {len(plugins)} 个", classes="sidebar-item")
