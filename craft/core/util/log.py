import logging
import os


class Log:
    LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}

    def __init__(self, service: str = "craft"):
        self.service = service
        self.level = self.LEVELS.get(os.environ.get("CRAFT_LOG_LEVEL", "info").lower(), 20)
        self._logger = logging.getLogger(service)

    @staticmethod
    def create(config: dict | None = None) -> "Log":
        return Log(service=(config or {}).get("service", "craft"))

    def debug(self, msg: str, **ctx):
        if self.level <= 10:
            self._logger.debug(f"[{self.service}] {msg} {self._fmt(ctx)}")

    def info(self, msg: str, **ctx):
        if self.level <= 20:
            self._logger.info(f"[{self.service}] {msg} {self._fmt(ctx)}")

    def warn(self, msg: str, **ctx):
        if self.level <= 30:
            self._logger.warning(f"[{self.service}] {msg} {self._fmt(ctx)}")

    def error(self, msg: str, **ctx):
        if self.level <= 40:
            self._logger.error(f"[{self.service}] {msg} {self._fmt(ctx)}")

    def _fmt(self, ctx: dict) -> str:
        return " ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else ""
