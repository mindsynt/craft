"""
Layer — 移植自 layer.ts

Effect Layer 组合，用于依赖注入。
"""

from __future__ import annotations

from typing import Any


class Layer:
    """简易 Effect Layer 组合器"""

    def __init__(self, services: dict | None = None):
        self._services = services or {}

    def provide(self, *others: "Layer") -> "Layer":
        """合并多个 Layer（后者的服务覆盖前者）"""
        combined = dict(self._services)
        for other in others:
            combined.update(other._services)
        return Layer(combined)

    def get(self, key: str) -> Any:
        return self._services.get(key)

    @staticmethod
    def merge(*layers: "Layer") -> "Layer":
        """合并所有 Layer"""
        result = Layer()
        for layer in layers:
            result._services.update(layer._services)
        return result
