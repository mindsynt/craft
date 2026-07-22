"""
工具函数库 — 移植自 packages/opencode/src/util/ (54文件综合)
日志、错误、文件系统、锁、超时、网络、格式化、键绑定
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ═══════════════════════════════════════════════════════════
# 日志 (log.ts)
# ═══════════════════════════════════════════════════════════

class Log:
    LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}

    def __init__(self, service: str = "craft"):
        self.service = service
        self.level = self.LEVELS.get(os.environ.get("CRAFT_LOG_LEVEL", "info").lower(), 20)
        self._logger = logging.getLogger(service)

    @staticmethod
    def create(config: dict | None = None) -> Log:
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


# ═══════════════════════════════════════════════════════════
# 错误处理 (error.ts)
# ═══════════════════════════════════════════════════════════

class NamedError(Exception):
    """具名错误，带结构化数据"""
    def __init__(self, name: str, message: str = "", data: dict | None = None):
        self.error_name = name
        self.data = data or {}
        super().__init__(message or name)


class ErrorCode:
    """标准错误码"""
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_INPUT = "INVALID_INPUT"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INTERNAL = "INTERNAL"


def create_named_error(name: str, schema: type | None = None):
    """创建具名错误工厂"""
    def factory(message: str = "", **kwargs):
        return NamedError(name, message, kwargs)
    factory.__name__ = name
    return factory


# ═══════════════════════════════════════════════════════════
# 函数工具 (fn.ts)
# ═══════════════════════════════════════════════════════════

def memoize(fn: Callable) -> Callable:
    """记忆化"""
    cache = {}
    def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = fn(*args, **kwargs)
        return cache[key]
    wrapper.cache = cache
    return wrapper


def debounce(fn: Callable, wait: float = 0.3):
    """防抖"""
    timer = [None]
    async def wrapper(*args, **kwargs):
        if timer[0]:
            timer[0].cancel()
        loop = asyncio.get_event_loop()
        timer[0] = loop.call_later(wait, lambda: asyncio.create_task(fn(*args, **kwargs)))
    return wrapper


def throttle(fn: Callable, interval: float = 1.0):
    """节流"""
    last = 0
    def wrapper(*args, **kwargs):
        nonlocal last
        now = time.time()
        if now - last >= interval:
            last = now
            return fn(*args, **kwargs)
    return wrapper


def pipe(value: Any, *fns: Callable) -> Any:
    """管道操作"""
    for fn in fns:
        value = fn(value)
    return value


def merge_deep(*dicts: dict) -> dict:
    """深度合并字典"""
    result = {}
    for d in dicts:
        for k, v in d.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = merge_deep(result[k], v)
            else:
                result[k] = v
    return result


# ═══════════════════════════════════════════════════════════
# 超时 (timeout.ts)
# ═══════════════════════════════════════════════════════════

class Timeout:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self._task: asyncio.Task | None = None
        self._timed_out = False

    async def __aenter__(self):
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, *args):
        if self._task:
            self._task.cancel()

    async def _run(self):
        await asyncio.sleep(self.seconds)
        self._timed_out = True

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    def check(self):
        if self._timed_out:
            raise TimeoutError(f"操作超时 ({self.seconds}s)")


async def with_timeout(coro, timeout: float, default=None):
    """带超时的异步执行"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


# ═══════════════════════════════════════════════════════════
# 文件系统 (filesystem.ts)
# ═══════════════════════════════════════════════════════════

class FileSystem:
    """文件系统操作"""

    @staticmethod
    async def read_text(path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception:
            return None

    @staticmethod
    async def write_text(path: str, content: str) -> bool:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    @staticmethod
    async def exists(path: str) -> bool:
        return Path(path).exists()

    @staticmethod
    async def remove(path: str) -> bool:
        try:
            p = Path(path)
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            return True
        except Exception:
            return False

    @staticmethod
    async def copy(src: str, dst: str) -> bool:
        try:
            shutil.copy2(src, dst)
            return True
        except Exception:
            return False

    @staticmethod
    async def list_dir(path: str, pattern: str | None = None) -> list[str]:
        try:
            p = Path(path)
            if pattern:
                return [str(f) for f in p.glob(pattern)]
            return [str(f) for f in p.iterdir()]
        except Exception:
            return []

    @staticmethod
    async def mkdir(path: str) -> bool:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════
# 工具命令 (which.ts)
# ═══════════════════════════════════════════════════════════

async def which(cmd: str) -> str | None:
    """查找可执行文件路径"""
    try:
        r = subprocess.run(["which", cmd], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# 锁 (lock.ts)
# ═══════════════════════════════════════════════════════════

class Lock:
    """异步锁"""
    def __init__(self):
        self._lock = asyncio.Lock()

    async def acquire(self):
        await self._lock.acquire()

    def release(self):
        self._lock.release()

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, *args):
        self._lock.release()


# ═══════════════════════════════════════════════════════════
# 格式化 (format.ts)
# ═══════════════════════════════════════════════════════════

def format_bytes(size: int) -> str:
    """格式化字节数"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f}{unit}" if isinstance(size, float) else f"{size}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds//60:.0f}m{seconds%60:.0f}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h:.0f}h{m:.0f}m"


def format_number(n: int) -> str:
    """格式化数字（千分位）"""
    return f"{n:,}"


def truncate(text: str, max_len: int = 200) -> str:
    """截断文本"""
    return text[:max_len] + "..." if len(text) > max_len else text


# ═══════════════════════════════════════════════════════════
# 网络 (network.ts)
# ═══════════════════════════════════════════════════════════

async def fetch_json(url: str, timeout: float = 10) -> dict | None:
    """HTTP GET 请求"""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# 键绑定 (keybind.ts)
# ═══════════════════════════════════════════════════════════

def parse_keybind(spec: str) -> dict:
    """解析键绑定字符串"""
    parts = spec.replace("-", " ").replace("+", " ").split()
    result = {"key": "", "modifiers": []}
    for p in parts:
        p = p.lower()
        if p in ("ctrl", "cmd", "meta", "alt", "shift", "option", "super"):
            result["modifiers"].append(p)
        else:
            result["key"] = p
    return result


# ═══════════════════════════════════════════════════════════
# 编码/哈希 (token.ts, data-url.ts)
# ═══════════════════════════════════════════════════════════

def generate_id(prefix: str = "") -> str:
    """生成唯一 ID"""
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════
# 地点/语言 (locale.ts)
# ═══════════════════════════════════════════════════════════

def get_system_locale() -> str:
    """获取系统语言"""
    import locale
    try:
        return locale.getdefaultlocale()[0] or "en_US"
    except Exception:
        return "en_US"


# init logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
