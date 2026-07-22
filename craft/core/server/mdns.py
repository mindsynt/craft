"""mDNS 服务发现 — 移植自 mdns.ts

使用 Zeroconf/Bonjour 发布 HTTP 服务以进行局域网发现。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_current_port: int | None = None
_service: Any = None


def publish(port: int, domain: str | None = None):
    """发布 mDNS 服务

    对应 TS publish()
    """
    global _current_port, _service

    if _current_port == port:
        return
    if _service:
        unpublish()

    host = domain or "craft.local"
    name = f"craft-{port}"

    try:
        from zeroconf import Zeroconf, ServiceInfo

        info = ServiceInfo(
            type_="_http._tcp.local.",
            name=f"{name}._http._tcp.local.",
            addresses=[],
            port=port,
            properties={"path": "/"},
            server=f"{host}.",
        )
        _service = Zeroconf()
        _service.register_service(info)
        _current_port = port
        logger.info("mDNS service published", extra={"name": name, "port": port})
    except ImportError:
        logger.warning("zeroconf not available; mDNS disabled")
    except Exception as err:
        logger.error("mDNS publish failed", extra={"error": str(err)})
        if _service:
            try:
                _service.close()
            except Exception:
                pass
        _service = None
        _current_port = None


def unpublish():
    """取消发布 mDNS 服务

    对应 TS unpublish()
    """
    global _service, _current_port

    if _service:
        try:
            _service.close()
        except Exception as err:
            logger.error("mDNS unpublish failed", extra={"error": str(err)})
        _service = None
        _current_port = None
        logger.info("mDNS service unpublished")
