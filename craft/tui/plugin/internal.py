"""
内部插件列表 — 移植自 plugin/internal.ts

内置 TUI 插件的注册列表。
"""

from __future__ import annotations

from typing import Any, Callable

# TUI Plugin 类型定义
TuiPluginFn = Callable  # async (api, options?, meta?) -> None

TuiPluginModule = dict  # {"id": str, "tui": TuiPluginFn}


def make_internal_plugin(plugin_id: str) -> dict:
    """创建内置 TUI 插件占位条目"""
    return {
        "id": plugin_id,
        "tui": lambda: None,  # no-op plugin
    }


# 内部 TUI 插件列表 — 与 TS 版一一对应
# 对应 feature-plugins/home/footer, home/tips, sidebar/*, system/plugins
INTERNAL_PLUGIN_IDS = [
    "craft:home-footer",
    "craft:home-tips",
    "craft:sidebar-context",
    "craft:sidebar-cwd",
    "craft:sidebar-instructions",
    "craft:sidebar-mcp",
    "craft:sidebar-lsp",
    "craft:sidebar-goal",
    "craft:sidebar-task",
    "craft:sidebar-todo",
    "craft:sidebar-files",
    "craft:sidebar-footer",
    "craft:plugin-manager",
]

INTERNAL_TUI_PLUGINS: list[dict] = [
    make_internal_plugin(pid) for pid in INTERNAL_PLUGIN_IDS
]
