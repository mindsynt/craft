"""
插件系统 — 移植自 packages/opencode/src/plugin/
支持：动态加载、生命周期钩子、依赖注入
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from typing import Any, Callable

from craft.config import CONFIG_DIR

logger = logging.getLogger(__name__)

PLUGIN_DIR = CONFIG_DIR / "plugins"


class PluginHook:
    """插件钩子"""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str):
        def decorator(fn: Callable):
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    def emit(self, event: str, *args, **kwargs):
        for handler in self._handlers.get(event, []):
            try:
                r = handler(*args, **kwargs)
                if hasattr(r, "__await__"):
                    import asyncio
                    asyncio.create_task(r)
            except Exception as e:
                logger.error(f"[Plugin Hook] {event}: {e}")


class PluginManifest:
    def __init__(self, name: str, version: str = "0.1.0", description: str = ""):
        self.name = name
        self.version = version
        self.description = description
        self.entry_point: str = ""
        self.dependencies: list[str] = []


class Plugin:
    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.module = None
        self.enabled = True
        self.hooks = PluginHook()

    def load(self):
        try:
            spec = importlib.util.spec_from_file_location(
                self.manifest.name, self.manifest.entry_point
            )
            if spec and spec.loader:
                self.module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.module)
                if hasattr(self.module, "setup"):
                    self.module.setup(self.hooks)
                logger.info(f"[Plugin] 加载: {self.manifest.name} v{self.manifest.version}")
                return True
        except Exception as e:
            logger.error(f"[Plugin] 加载失败 {self.manifest.name}: {e}")
        return False

    def unload(self):
        if hasattr(self.module, "teardown"):
            try:
                self.module.teardown()
            except Exception as e:
                logger.error(f"[Plugin] 卸载失败 {self.manifest.name}: {e}")
        self.module = None
        self.enabled = False


class PluginManager:
    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._global_hooks = PluginHook()

    def discover(self, directory: str | None = None):
        dir_path = directory or str(PLUGIN_DIR)
        if not os.path.isdir(dir_path):
            return
        for entry in os.listdir(dir_path):
            plugin_dir = os.path.join(dir_path, entry)
            if not os.path.isdir(plugin_dir):
                continue
            manifest_file = os.path.join(plugin_dir, "plugin.json")
            if os.path.exists(manifest_file):
                import json
                try:
                    data = json.loads(open(manifest_file).read())
                    manifest = PluginManifest(
                        name=data.get("name", entry),
                        version=data.get("version", "0.1.0"),
                        description=data.get("description", ""),
                    )
                    manifest.entry_point = os.path.join(plugin_dir, data.get("main", "main.py"))
                    if os.path.exists(manifest.entry_point):
                        plugin = Plugin(manifest)
                        self._plugins[manifest.name] = plugin
                        logger.info(f"[Plugin] 发现: {manifest.name}")
                except Exception as e:
                    logger.error(f"[Plugin] 读取失败 {entry}: {e}")

    def install(self, manifest: PluginManifest) -> Plugin:
        plugin = Plugin(manifest)
        self._plugins[manifest.name] = plugin
        return plugin

    def load_all(self):
        for name, plugin in self._plugins.items():
            if plugin.enabled:
                plugin.load()

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def list(self) -> list[dict]:
        return [{"name": p.manifest.name, "version": p.manifest.version,
                 "description": p.manifest.description, "enabled": p.enabled}
                for p in self._plugins.values()]

    def unload_all(self):
        for plugin in self._plugins.values():
            plugin.unload()

    @property
    def hooks(self) -> PluginHook:
        return self._global_hooks


plugin_manager = PluginManager()
