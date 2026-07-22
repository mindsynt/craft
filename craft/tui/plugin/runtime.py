"""
TUI 插件运行时 — 移植自 plugin/runtime.ts

插件加载、激活、停用、生命周期管理。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional

from craft.tui.plugin.internal import INTERNAL_TUI_PLUGINS

logger = logging.getLogger(__name__)

DISPOSE_TIMEOUT_MS = 5000
KV_KEY = "plugin_enabled"

# ─── 类型定义 ─────────────────────────────────

PluginSource = str  # "internal" | "file" | "npm"
PluginState = str  # "first" | "same" | "updated"

PluginStatus = dict  # {id, source, spec, target, enabled, active}


class PluginScope:
    """插件作用域 — 生命周期管理"""

    def __init__(self, load: dict, plugin_id: str):
        self._ctrl = asyncio.Event()
        self._dispose_fns: list[Callable] = []
        self._done = False
        self._plugin_id = plugin_id

    @property
    def signal(self):
        return self._ctrl.is_set()

    def on_dispose(self, fn: Callable) -> Callable:
        """注册清理函数"""
        if self._done:
            return lambda: None
        self._dispose_fns.append(fn)

        def _unsubscribe():
            if fn in self._dispose_fns:
                self._dispose_fns.remove(fn)

        return _unsubscribe

    def track(self, fn: Optional[Callable]) -> Callable:
        """跟踪清理函数"""
        if not fn:
            return lambda: None
        self._dispose_fns.append(fn)
        return fn

    def dispose(self):
        """清理所有资源"""
        if self._done:
            return
        self._done = True
        self._ctrl.set()
        for fn in reversed(self._dispose_fns):
            try:
                fn()
            except Exception as e:
                logger.warning("Plugin cleanup error: %s", e)
        self._dispose_fns.clear()


# ─── 运行时状态 ──────────────────────────────


class PluginEntry:
    """插件条目"""

    def __init__(self, plugin_id: str, load: dict, meta: dict, themes: dict, plugin_fn, enabled: bool = True):
        self.id = plugin_id
        self.load = load
        self.meta = meta
        self.themes = themes
        self.plugin = plugin_fn
        self.enabled = enabled
        self.scope: Optional[PluginScope] = None


class RuntimeState:
    """运行时状态"""

    def __init__(self, directory: str, api: Any, slots: Any):
        self.directory = directory
        self.api = api
        self.slots = slots
        self.plugins: list[PluginEntry] = []
        self.plugins_by_id: dict[str, PluginEntry] = {}
        self.pending: dict[str, dict] = {}


# ─── 工具函数 ─────────────────────────────────

def _error_message(err: Any) -> str:
    return str(err) if err else "unknown error"


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


# ─── 运行时实现 ──────────────────────────────

_runtime: Optional[RuntimeState] = None
_loaded: Optional[asyncio.Task] = None
_dir = ""


async def init(input_data: dict):
    """初始化插件运行时"""
    global _runtime, _loaded, _dir

    cwd = os.getcwd()
    if _loaded is not None:
        if _dir != cwd:
            raise RuntimeError(
                f"TuiPluginRuntime.init() called with different cwd. "
                f"expected={_dir} got={cwd}"
            )
        return await _loaded

    _dir = cwd
    _loaded = asyncio.create_task(_load(input_data))
    return await _loaded


def list_plugins() -> list[PluginStatus]:
    """列出所有插件状态"""
    if not _runtime:
        return []
    return [
        {
            "id": p.id,
            "source": p.meta.get("source", ""),
            "spec": p.meta.get("spec", ""),
            "target": p.meta.get("target", ""),
            "enabled": p.enabled,
            "active": p.scope is not None,
        }
        for p in _runtime.plugins
    ]


async def activate_plugin(plugin_id: str) -> bool:
    """激活插件"""
    return await _activate_plugin_by_id(_runtime, plugin_id, True)


async def deactivate_plugin(plugin_id: str) -> bool:
    """停用插件"""
    return await _deactivate_plugin_by_id(_runtime, plugin_id, True)


async def add_plugin(spec: str) -> bool:
    """添加插件"""
    return await _add_plugin_by_spec(_runtime, spec)


async def install_plugin(spec: str, options: Optional[dict] = None) -> dict:
    """安装插件"""
    return await _install_plugin_by_spec(_runtime, spec, options)


async def dispose():
    """释放所有插件"""
    global _loaded, _dir, _runtime
    task = _loaded
    _loaded = None
    _dir = ""
    if task:
        await task
    state = _runtime
    _runtime = None
    if not state:
        return
    for plugin in reversed(state.plugins):
        await _deactivate_plugin_entry(state, plugin, False)


async def reload(input_data: dict):
    """重新加载插件"""
    await dispose()
    return await init(input_data)


# ─── 内部实现 ─────────────────────────────────

async def _load(input_data: dict):
    """实际加载逻辑"""
    global _runtime

    api = input_data.get("api")
    config = input_data.get("config", {})
    cwd = os.getcwd()
    slots = _setup_slots(api)

    state = RuntimeState(cwd, api, slots)
    _runtime = state

    try:
        # Load internal plugins
        for item in INTERNAL_TUI_PLUGINS:
            plugin_id = item.get("id", "unknown")
            entry = PluginEntry(
                plugin_id=plugin_id,
                load={"spec": plugin_id, "target": plugin_id, "source": "internal", "options": None},
                meta={"state": "same", "id": plugin_id, "source": "internal", "spec": plugin_id,
                      "target": plugin_id, "first_time": 0, "last_time": 0, "time_changed": 0, "load_count": 1},
                themes={},
                plugin_fn=item.get("tui", lambda: None),
                enabled=True,
            )
            state.plugins_by_id[plugin_id] = entry
            state.plugins.append(entry)

        # Activate plugins
        for plugin in state.plugins:
            if not plugin.enabled:
                continue
            await _activate_plugin_entry(state, plugin, False)

    except Exception as e:
        logger.error("Failed to load TUI plugins: %s", e)


def _setup_slots(api) -> Any:
    """设置插槽系统"""
    return {"_api": api}


async def _activate_plugin_entry(state: RuntimeState, plugin: PluginEntry, persist: bool) -> bool:
    """激活单个插件"""
    plugin.enabled = True
    if plugin.scope:
        return True

    scope = PluginScope(plugin.load, plugin.id)
    try:
        if asyncio.iscoroutinefunction(plugin.plugin):
            await plugin.plugin()
        else:
            plugin.plugin()
        plugin.scope = scope
        return True
    except Exception as e:
        logger.error("Failed to activate plugin %s: %s", plugin.id, e)
        scope.dispose()
        return False


async def _deactivate_plugin_entry(state: RuntimeState, plugin: PluginEntry, persist: bool) -> bool:
    """停用单个插件"""
    plugin.enabled = False
    if not plugin.scope:
        return True
    plugin.scope.dispose()
    plugin.scope = None
    return True


async def _activate_plugin_by_id(state: Optional[RuntimeState], plugin_id: str, persist: bool) -> bool:
    if not state:
        return False
    plugin = state.plugins_by_id.get(plugin_id)
    if not plugin:
        return False
    return await _activate_plugin_entry(state, plugin, persist)


async def _deactivate_plugin_by_id(state: Optional[RuntimeState], plugin_id: str, persist: bool) -> bool:
    if not state:
        return False
    plugin = state.plugins_by_id.get(plugin_id)
    if not plugin:
        return False
    return await _deactivate_plugin_entry(state, plugin, persist)


async def _add_plugin_by_spec(state: Optional[RuntimeState], spec: str) -> bool:
    if not state:
        return False
    spec = spec.strip()
    if not spec:
        return False
    # Simplified: just add a placeholder entry
    plugin_id = spec.split("/")[-1] if "/" in spec else spec
    entry = PluginEntry(
        plugin_id=plugin_id,
        load={"spec": spec, "target": spec, "source": "file", "options": None},
        meta={"state": "first", "id": plugin_id, "source": "file", "spec": spec,
              "target": spec, "first_time": 0, "last_time": 0, "time_changed": 0, "load_count": 1},
        themes={},
        plugin_fn=lambda: None,
        enabled=True,
    )
    if plugin_id in state.plugins_by_id:
        return True
    state.plugins_by_id[plugin_id] = entry
    state.plugins.append(entry)
    return await _activate_plugin_entry(state, entry, False)


async def _install_plugin_by_spec(state: Optional[RuntimeState], spec: str, options: Optional[dict]) -> dict:
    if not state:
        return {"ok": False, "message": "Plugin runtime is not ready."}
    if not spec.strip():
        return {"ok": False, "message": "Plugin package name is required"}
    return {"ok": True, "dir": "", "tui": False}


# ─── 导出 ──────────────────────────────────

class TuiPluginRuntime:
    """TUI 插件运行时命名空间"""
    init = staticmethod(init)
    list = staticmethod(list_plugins)
    activate = staticmethod(activate_plugin)
    deactivate = staticmethod(deactivate_plugin)
    add = staticmethod(add_plugin)
    install = staticmethod(install_plugin)
    dispose = staticmethod(dispose)
    reload = staticmethod(reload)
