"""插件管理器 — PluginManager, Plugin, PluginHook"""

from __future__ import annotations

import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .shared import (
    PLUGIN_DIR,
)

logger = logging.getLogger(__name__)


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


# ──────────────────────────────────────────────
# 内部插件注册表
# ──────────────────────────────────────────────

def _build_internal_plugins() -> list[dict[str, Any]]:
    """构建内部插件列表（延迟导入避免循环依赖）"""
    from .xai import make_xai_auth_plugin
    from .mimo import make_mimo_auth_plugin, make_anthropic_proxy_plugin
    from .codex import make_codex_auth_plugin
    from .copilot import make_copilot_auth_plugin
    from .cloudflare import make_cloudflare_workers_auth_plugin, make_cloudflare_ai_gateway_auth_plugin
    from .hook_plugins import make_checkpoint_splitover_plugin, make_subagent_progress_checker_plugin

    return [
        make_mimo_auth_plugin(),
        make_anthropic_proxy_plugin(),
        make_codex_auth_plugin(),
        make_xai_auth_plugin(),
        make_copilot_auth_plugin(),
        make_cloudflare_workers_auth_plugin(),
        make_cloudflare_ai_gateway_auth_plugin(),
        make_checkpoint_splitover_plugin(),
        make_subagent_progress_checker_plugin(),
    ]


def get_internal_plugins() -> list[dict[str, Any]]:
    """获取内置插件列表"""
    return _build_internal_plugins()
