"""
插件系统索引 — 移植自 plugin/index.ts

导出 TuiPluginRuntime, createTuiApi, RouteMap。
"""

from __future__ import annotations

from craft.tui.plugin.runtime import TuiPluginRuntime
from craft.tui.plugin.internal import INTERNAL_TUI_PLUGINS

__all__ = ["TuiPluginRuntime", "INTERNAL_TUI_PLUGINS"]
