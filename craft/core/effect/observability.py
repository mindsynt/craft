"""可观测性 — ObservabilityConfig, Observability"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, NamedTuple

from .logger import EffectLogger


class ObservabilityConfig(NamedTuple):
    enabled: bool
    endpoint: str | None = None
    headers: dict[str, str] | None = None
    service_name: str = "craft"
    service_version: str = "0.1.0"


_observability_config = ObservabilityConfig(enabled=False)
_process_id = str(uuid.uuid4())


class Observability:
    """
    可观测性层 — 对应 observability.ts
    支持 OTLP 日志和追踪, 默认为空操作
    """

    config: ObservabilityConfig = _observability_config

    @classmethod
    def configure(
        cls,
        endpoint: str | None = None,
        headers: str | None = None,
        service_name: str = "craft",
        service_version: str = "0.1.0",
    ) -> None:
        parsed_headers: dict[str, str] | None = None
        if headers:
            parsed_headers = {}
            for part in headers.split(","):
                if "=" in part:
                    key, _, value = part.partition("=")
                    parsed_headers[key.strip()] = value.strip()

        cls.config = ObservabilityConfig(
            enabled=bool(endpoint),
            endpoint=endpoint,
            headers=parsed_headers,
            service_name=service_name,
            service_version=service_version,
        )
        if cls.config.enabled:
            EffectLogger.configure(logging.DEBUG)

    @classmethod
    def resource(cls) -> dict[str, str]:
        return {
            "service.name": cls.config.service_name,
            "service.version": cls.config.service_version,
            "deployment.environment.name": os.environ.get(
                "INSTALLATION_CHANNEL", "development"
            ),
            "service.instance.id": _process_id,
        }

    @classmethod
    def layer(cls, logger_layer: Any = None) -> Any:
        """返回可观测性层 (装饰器形式, 兼容现有框架)"""
        # 如果未启用 OTLP，仅使用 EffectLogger
        return logger_layer or EffectLogger


__all__ = [
    "ObservabilityConfig",
    "Observability",
]
