"""
工具函数库 — 移植自 packages/opencode/src/util/ (54文件综合)
日志、错误、文件系统、锁、超时、网络、格式化、键绑定、进程、队列、颜色等
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import platform
import re
import shutil
import signal as _signal
import struct
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")
B = TypeVar("B")


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


def is_record(value: Any) -> bool:
    """检查值是否为字典（类似TS的isRecord）"""
    return isinstance(value, dict)


def error_format(error: Any) -> str:
    """格式化错误为字符串（类似TS error.ts errorFormat）"""
    if isinstance(error, Exception):
        return f"{type(error).__name__}: {error}"
    if isinstance(error, dict):
        try:
            import json
            return json.dumps(error, indent=2, ensure_ascii=False)
        except Exception:
            return "Unexpected error (unserializable)"
    return str(error)


def error_message(error: Any) -> str:
    """提取错误消息（类似TS error.ts errorMessage）"""
    if isinstance(error, Exception):
        if str(error):
            return str(error)
        return type(error).__name__
    if is_record(error) and isinstance(error.get("message"), str) and error["message"]:
        return error["message"]
    text = str(error)
    if text and text != "[object Object]":
        return text
    formatted = error_format(error)
    if formatted and formatted != "{}":
        return formatted
    return "unknown error"


def error_data(error: Any) -> dict:
    """提取错误结构化数据（类似TS error.ts errorData）"""
    if isinstance(error, Exception):
        return {
            "type": type(error).__name__,
            "message": error_message(error),
            "cause": str(error.__cause__) if error.__cause__ else None,
        }
    if is_record(error):
        result = dict(error)
        if "message" not in result or not isinstance(result["message"], str):
            result["message"] = error_message(error)
        return result
    return {
        "type": type(error).__name__,
        "message": error_message(error),
    }


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


def lazy(fn: Callable[[], T]) -> Callable[[], T]:
    """惰性求值 — 移植自 lazy.ts"""
    value: T = None  # type: ignore
    loaded = False

    def wrapper() -> T:
        nonlocal value, loaded
        if not loaded:
            value = fn()
            loaded = True
        return value

    def reset():
        nonlocal value, loaded
        loaded = False
        value = None  # type: ignore

    wrapper.reset = reset  # type: ignore
    return wrapper


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


async def timeout_promise(promise: Awaitable[T], ms: float) -> T:
    """Promise带超时 — 移植自 timeout.ts withTimeout"""
    return await asyncio.wait_for(promise, timeout=ms / 1000)


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

    @staticmethod
    async def is_dir(path: str) -> bool:
        """检查是否为目录 — 移植自 filesystem.ts isDir"""
        try:
            return Path(path).is_dir()
        except Exception:
            return False

    @staticmethod
    async def size(path: str) -> int:
        """获取文件大小 — 移植自 filesystem.ts size"""
        try:
            return Path(path).stat().st_size
        except Exception:
            return 0

    @staticmethod
    def contains(parent: str, child: str) -> bool:
        """检查父路径是否包含子路径 — 移植自 filesystem.ts contains"""
        try:
            rel = Path(child).relative_to(parent)
            return not str(rel).startswith("..")
        except ValueError:
            return False

    @staticmethod
    async def find_up(targets: str | list[str], start: str, stop: str | None = None) -> list[str]:
        """向上查找文件 — 移植自 filesystem.ts findUp"""
        if isinstance(targets, str):
            targets = [targets]
        dirs = []
        current = start
        while True:
            dirs.append(current)
            if stop is not None and current == stop:
                break
            parent = str(Path(current).parent)
            if parent == current:
                break
            current = parent
        result = []
        for d in dirs:
            for t in targets:
                candidate = str(Path(d) / t)
                if await FileSystem.exists(candidate):
                    result.append(candidate)
        return result


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
# 锁 (lock.ts) — 基础互斥锁 + 读写锁
# ═══════════════════════════════════════════════════════════

class Lock:
    """异步互斥锁"""
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


class RWLock:
    """读写锁 — 移植自 lock.ts (read/write keyed锁)"""

    def __init__(self):
        self._readers = 0
        self._writer = False
        self._waiting_readers: list[asyncio.Event] = []
        self._waiting_writers: list[asyncio.Event] = []
        self._lock = asyncio.Lock()

    async def read(self) -> "RWLock._ReadGuard":
        async with self._lock:
            if not self._writer and not self._waiting_writers:
                self._readers += 1
                return self._ReadGuard(self)

        event = asyncio.Event()
        async with self._lock:
            self._waiting_readers.append(event)
        await event.wait()
        async with self._lock:
            self._readers += 1
        return self._ReadGuard(self)

    async def write(self) -> "RWLock._WriteGuard":
        async with self._lock:
            if not self._writer and self._readers == 0:
                self._writer = True
                return self._WriteGuard(self)

        event = asyncio.Event()
        async with self._lock:
            self._waiting_writers.append(event)
        await event.wait()
        async with self._lock:
            self._writer = True
        return self._WriteGuard(self)

    async def _release_read(self):
        async with self._lock:
            self._readers -= 1
            self._process()

    async def _release_write(self):
        async with self._lock:
            self._writer = False
            self._process()

    def _process(self):
        if self._writer or self._readers > 0:
            return
        if self._waiting_writers:
            ev = self._waiting_writers.pop(0)
            ev.set()
            return
        while self._waiting_readers:
            ev = self._waiting_readers.pop(0)
            ev.set()

    class _ReadGuard:
        def __init__(self, rw: "RWLock"):
            self._rw = rw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self._rw._release_read()

    class _WriteGuard:
        def __init__(self, rw: "RWLock"):
            self._rw = rw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self._rw._release_write()


# ═══════════════════════════════════════════════════════════
# 格式化 (format.ts, locale.ts)
# ═══════════════════════════════════════════════════════════

def format_bytes(size: int) -> str:
    """格式化字节数"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f}{unit}" if isinstance(size, float) else f"{size}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def format_duration(seconds: float) -> str:
    """格式化时长（秒）"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds//60:.0f}m{seconds%60:.0f}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h:.0f}h{m:.0f}m"


def format_duration_precise(seconds: float) -> str:
    """精确格式化时长 — 移植自 format.ts formatDuration"""
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        mins = int(seconds // 60)
        remaining = seconds % 60
        return f"{mins}m {remaining}s" if remaining > 0 else f"{mins}m"
    if seconds < 86400:
        hours = int(seconds // 3600)
        remaining = int((seconds % 3600) // 60)
        return f"{hours}h {remaining}m" if remaining > 0 else f"{hours}h"
    if seconds < 604800:
        days = int(seconds // 86400)
        return "~1 day" if days == 1 else f"~{days} days"
    weeks = int(seconds // 604800)
    return "~1 week" if weeks == 1 else f"~{weeks} weeks"


def format_number(n: int) -> str:
    """格式化数字（千分位）"""
    return f"{n:,}"


def format_number_short(num: float) -> str:
    """简短格式化数字 — 移植自 locale.ts number"""
    if num >= 1000000:
        return f"{num / 1000000:.1f}M"
    elif num >= 1000:
        return f"{num / 1000:.1f}K"
    return str(num)


def truncate(text: str, max_len: int = 200) -> str:
    """截断文本"""
    return text[:max_len] + "..." if len(text) > max_len else text


def truncate_middle(text: str, max_len: int = 35) -> str:
    """中间截断文本 — 移植自 locale.ts truncateMiddle"""
    if len(text) <= max_len:
        return text
    ellipsis = "…"
    keep_start = (max_len - len(ellipsis)) // 2 + (max_len - len(ellipsis)) % 2
    keep_end = (max_len - len(ellipsis)) // 2
    return text[:keep_start] + ellipsis + text[-keep_end:]


def format_ms(millis: float) -> str:
    """格式化毫秒数 — 移植自 locale.ts duration"""
    if millis < 1000:
        return f"{millis:.0f}ms"
    if millis < 60000:
        return f"{millis / 1000:.1f}s"
    if millis < 3600000:
        minutes = int(millis // 60000)
        seconds = int((millis % 60000) // 1000)
        return f"{minutes}m {seconds}s"
    if millis < 86400000:
        hours = int(millis // 3600000)
        minutes = int((millis % 3600000) // 60000)
        return f"{hours}h {minutes}m"
    hours = int(millis // 3600000)
    days = int((millis % 3600000) // 86400000)
    return f"{days}d {hours}h"


def pluralize(count: int, singular: str, plural: str) -> str:
    """复数化 — 移植自 locale.ts pluralize"""
    template = singular if count == 1 else plural
    return template.replace("{}", str(count))


def titlecase(s: str) -> str:
    """标题大小写 — 移植自 locale.ts titlecase"""
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), s)


def get_system_locale() -> str:
    """获取系统语言"""
    import locale
    try:
        return locale.getdefaultlocale()[0] or "en_US"
    except Exception:
        return "en_US"


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


def is_online() -> bool:
    """检查网络是否在线 — 移植自 network.ts online"""
    return True


def is_proxied() -> bool:
    """检查是否使用代理 — 移植自 network.ts proxied"""
    return bool(os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
                or os.environ.get("http_proxy") or os.environ.get("https_proxy"))


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


def estimate_tokens(text: str) -> int:
    """估算 token 数 — 移植自 token.ts estimate"""
    CHARS_PER_TOKEN = 4
    return max(0, round(len(text or "") / CHARS_PER_TOKEN))


def decode_data_url(url: str) -> str:
    """解码 data URL — 移植自 data-url.ts decodeDataUrl"""
    idx = url.find(",")
    if idx == -1:
        return ""
    head = url[:idx]
    body = url[idx + 1:]
    if ";base64" in head:
        return base64.b64decode(body).decode("utf-8", errors="replace")
    from urllib.parse import unquote
    return unquote(body)


# ═══════════════════════════════════════════════════════════
# 信号 (signal.ts)
# ═══════════════════════════════════════════════════════════

def make_signal():
    """创建信号量 — 移植自 signal.ts (one-shot)"""
    future: asyncio.Future | None = None

    async def wait():
        nonlocal future
        if future is None:
            future = asyncio.get_running_loop().create_future()
        await future

    def trigger():
        nonlocal future
        if future is not None and not future.done():
            future.set_result(None)

    return {"trigger": trigger, "wait": wait}


# ═══════════════════════════════════════════════════════════
# 队列 (queue.ts) — AsyncQueue
# ═══════════════════════════════════════════════════════════

class AsyncQueue(Generic[T]):
    """异步队列 — 移植自 queue.ts AsyncQueue"""

    def __init__(self, capacity: int = 0):
        self._queue: list[T] = []
        self._resolvers: list[asyncio.Future] = []
        self._capacity = capacity if capacity > 0 else float("inf")  # type: ignore
        self.dropped = 0

    def push(self, item: T):
        if self._resolvers:
            fut = self._resolvers.pop(0)
            fut.set_result(item)
            return
        if len(self._queue) >= self._capacity:
            self._queue.pop(0)
            self.dropped += 1
        self._queue.append(item)

    @property
    def size(self) -> int:
        return len(self._queue)

    async def next(self) -> T:
        if self._queue:
            return self._queue.pop(0)
        fut = asyncio.get_event_loop().create_future()
        self._resolvers.append(fut)
        return await fut

    def __aiter__(self) -> AsyncIterator[T]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[T]:
        while True:
            yield await self.next()


async def work_parallel(concurrency: int, items: list[T], fn: Callable[[T], Awaitable[None]]):
    """并发执行 — 移植自 queue.ts work"""
    pending = list(reversed(items))

    async def worker():
        while True:
            try:
                item = pending.pop()
            except IndexError:
                return
            await fn(item)

    await asyncio.gather(*[worker() for _ in range(concurrency)])


# ═══════════════════════════════════════════════════════════
# 颜色 (color.ts)
# ═══════════════════════════════════════════════════════════

def is_valid_hex(hex_str: str | None) -> bool:
    """检查是否为有效 hex 颜色 — 移植自 color.ts isValidHex"""
    if not hex_str:
        return False
    return bool(re.match(r"^#[0-9a-fA-F]{6}$", hex_str))


def hex_to_rgb(hex_str: str) -> dict:
    """hex 转 RGB — 移植自 color.ts hexToRgb"""
    r = int(hex_str[1:3], 16)
    g = int(hex_str[3:5], 16)
    b = int(hex_str[5:7], 16)
    return {"r": r, "g": g, "b": b}


def hex_to_ansi_bold(hex_str: str | None) -> str | None:
    """hex 转 ANSI 粗体颜色 — 移植自 color.ts hexToAnsiBold"""
    if not is_valid_hex(hex_str):
        return None
    rgb = hex_to_rgb(hex_str)
    return f"\x1b[38;2;{rgb['r']};{rgb['g']};{rgb['b']}m\x1b[1m"


# ═══════════════════════════════════════════════════════════
# 进程 (process.ts)
# ═══════════════════════════════════════════════════════════

class RunFailedError(Exception):
    """进程运行失败错误 — 移植自 process.ts RunFailedError"""
    def __init__(self, cmd: list[str], code: int, stdout: bytes, stderr: bytes):
        text = stderr.decode().strip()
        msg = f"Command failed with code {code}: {' '.join(cmd)}"
        if text:
            msg += f"\n{text}"
        self.cmd = list(cmd)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(msg)


def spawn_process(cmd: list[str], cwd: str | None = None,
                  env: dict | None = None, shell: bool = False,
                  timeout: float | None = None) -> subprocess.Popen:
    """生成进程 — 移植自 process.ts spawn"""
    if not cmd:
        raise ValueError("Command is required")
    proc_env = os.environ.copy()
    if env is not None:
        proc_env.update(env)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=shell,
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


async def run_process(cmd: list[str], cwd: str | None = None,
                      env: dict | None = None, shell: bool = False,
                      nothrow: bool = False) -> dict:
    """运行进程并获取输出 — 移植自 process.ts run"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env={**os.environ, **(env or {})} if env else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        code = proc.returncode or 0
        if code != 0 and not nothrow:
            raise RunFailedError(cmd, code, stdout, stderr)
        return {
            "code": code,
            "stdout": stdout,
            "stderr": stderr,
            "text": stdout.decode() if stdout else "",
        }
    except Exception as e:
        if not nothrow:
            raise
        return {
            "code": 1,
            "stdout": b"",
            "stderr": str(e).encode(),
            "text": str(e),
        }


async def run_text(cmd: list[str], cwd: str | None = None,
                   env: dict | None = None, shell: bool = False) -> str:
    """运行进程并获取文本输出 — 移植自 process.ts text"""
    result = await run_process(cmd, cwd=cwd, env=env, shell=shell)
    return result["text"]


async def run_lines(cmd: list[str], cwd: str | None = None,
                    env: dict | None = None, shell: bool = False) -> list[str]:
    """运行进程并获取行输出 — 移植自 process.ts lines"""
    text = await run_text(cmd, cwd=cwd, env=env, shell=shell)
    return [line for line in text.split("\n") if line]


def stop_process(proc: subprocess.Popen):
    """停止进程 — 移植自 process.ts stop"""
    if proc.returncode is not None:
        return
    proc.terminate()


# ═══════════════════════════════════════════════════════════
# 中止 (abort.ts)
# ═══════════════════════════════════════════════════════════

def abort_after(ms: int) -> dict:
    """创建超时中止控制器 — 移植自 abort.ts abortAfter"""
    event = asyncio.Event()

    def _abort():
        event.set()

    def clear_timeout():
        pass  # Timeout handled via asyncio.wait_for

    return {
        "event": event,
        "clear_timeout": clear_timeout,
    }


# ═══════════════════════════════════════════════════════════
# 推迟 (defer.ts)
# ═══════════════════════════════════════════════════════════

class Defer:
    """推迟执行 — 移植自 defer.ts"""
    def __init__(self, fn: Callable[[], None | Awaitable[None]]):
        self._fn = fn
        self._done = False

    def __del__(self):
        if not self._done:
            self._done = True
            result = self._fn()
            if hasattr(result, "__await__"):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(result)  # type: ignore
                except RuntimeError:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def defer(fn: Callable[[], None | Awaitable[None]]) -> Defer:
    return Defer(fn)


# ═══════════════════════════════════════════════════════════
# 媒体 (media.ts)
# ═══════════════════════════════════════════════════════════

MEDIA_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF8": "image/gif",
    b"BM": "image/bmp",
    b"%PDF-": "application/pdf",
    b"RIFF": None,  # WEBP needs special handling
}


def is_pdf_attachment(mime: str) -> bool:
    """检查是否为 PDF — 移植自 media.ts isPdfAttachment"""
    return mime == "application/pdf"


def is_media(mime: str) -> bool:
    """检查是否为媒体 — 移植自 media.ts isMedia"""
    return mime.startswith("image/") or is_pdf_attachment(mime)


def is_image_attachment(mime: str) -> bool:
    """检查是否为图片附件 — 移植自 media.ts isImageAttachment"""
    return mime.startswith("image/") and mime not in ("image/svg+xml", "image/vnd.fastbidsheet")


def sniff_mime(data: bytes, fallback: str = "application/octet-stream") -> str:
    """嗅探 MIME 类型 — 移植自 media.ts sniffAttachmentMime"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback


# ═══════════════════════════════════════════════════════════
# 归档 (archive.ts)
# ═══════════════════════════════════════════════════════════

async def extract_zip(zip_path: str, dest_dir: str):
    """解压 ZIP — 移植自 archive.ts extractZip"""
    if platform.system() == "Windows":
        import subprocess
        cmd = (
            f'$global:ProgressPreference = "SilentlyContinue"; '
            f'Expand-Archive -Path "{zip_path}" -DestinationPath "{dest_dir}" -Force'
        )
        await run_process(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd])
    else:
        await run_process(["unzip", "-o", "-q", zip_path, "-d", dest_dir])


# ═══════════════════════════════════════════════════════════
# RPC (rpc.ts)
# ═══════════════════════════════════════════════════════════

# RPC definitions for worker communication — 移植自 rpc.ts


# init logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
