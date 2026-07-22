"""效果日志器 — EffectLogger, EffectLoggerHandle"""

from __future__ import annotations

import logging
from typing import Any


Fields = dict[str, Any]


def _normalize_key(key: str) -> str:
    return "session.id" if key == "sessionID" else key


def _clean(input_fields: Fields | None) -> Fields:
    if not input_fields:
        return {}
    return {
        _normalize_key(k): v
        for k, v in input_fields.items()
        if v is not None
    }


def _text(input_val: Any) -> str:
    if isinstance(input_val, list):
        return " ".join(str(item) for item in input_val)
    return "" if input_val is None else str(input_val)


class EffectLoggerHandle:
    """Logger Handle — 提供有额外字段的日志方法"""

    def __init__(self, base: Fields | None = None):
        self._base = _clean(base)

    def debug(self, msg: Any = None, extra: Fields | None = None) -> None:
        ann = _clean({**self._base, **(extra or {})})
        logger = logging.getLogger("effect")
        extra_str = f" {ann}" if ann else ""
        logger.debug(f"{_text(msg)}{extra_str}")

    def info(self, msg: Any = None, extra: Fields | None = None) -> None:
        ann = _clean({**self._base, **(extra or {})})
        logger = logging.getLogger("effect")
        extra_str = f" {ann}" if ann else ""
        logger.info(f"{_text(msg)}{extra_str}")

    def warn(self, msg: Any = None, extra: Fields | None = None) -> None:
        ann = _clean({**self._base, **(extra or {})})
        logger = logging.getLogger("effect")
        extra_str = f" {ann}" if ann else ""
        logger.warning(f"{_text(msg)}{extra_str}")

    def error(self, msg: Any = None, extra: Fields | None = None) -> None:
        ann = _clean({**self._base, **(extra or {})})
        logger = logging.getLogger("effect")
        extra_str = f" {ann}" if ann else ""
        logger.error(f"{_text(msg)}{extra_str}")

    def with_fields(self, extra: Fields) -> EffectLoggerHandle:
        return EffectLoggerHandle(base={**self._base, **extra})


class EffectLogger:
    """效果日志器 — 对应 logger.ts"""

    @staticmethod
    def create(base: Fields | None = None) -> EffectLoggerHandle:
        return EffectLoggerHandle(base=base)

    @staticmethod
    def configure(level: int = logging.INFO) -> None:
        logging.basicConfig(level=level, format="%(levelname)s %(message)s")
        logging.getLogger("effect").setLevel(level)


__all__ = [
    "Fields",
    "EffectLoggerHandle",
    "EffectLogger",
]
