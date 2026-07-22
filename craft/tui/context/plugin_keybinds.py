"""
Plugin Keybinds 上下文 — 移植自 context/plugin-keybinds.ts

创建插件快捷键映射，支持覆盖。
"""

from __future__ import annotations

from typing import Any, Optional


class PluginKeybind:
    """插件快捷键管理器"""

    def __init__(
        self,
        base: dict,
        defaults: dict[str, str],
        overrides: Optional[dict] = None,
    ):
        self._base = base
        resolved: dict[str, str] = {}
        for name, default_value in defaults.items():
            override = overrides.get(name) if overrides else None
            resolved[name] = str(override) if override is not None and isinstance(override, str) and override.strip() else default_value
        self._all = resolved

    @property
    def all(self) -> dict[str, str]:
        """获取所有键绑定"""
        return dict(self._all)

    def get(self, name: str) -> str:
        """获取指定键绑定"""
        return self._all.get(name, name)

    def match(self, name: str, evt: Any) -> bool:
        """检查键盘事件是否匹配"""
        key = self.get(name)
        return self._base.get("match", lambda k, e: False)(key, evt)

    def print(self, name: str) -> str:
        """打印键绑定的可读形式"""
        key = self.get(name)
        printer = self._base.get("print", lambda k: k)
        return printer(key)
