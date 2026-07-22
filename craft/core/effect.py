"""
Effect 适配 — 移植自 packages/opencode/src/effect/
Effect-TS 的 Python 等价模式

移植文件清单 (14 个 TS → Python):
  - index.ts
  - instance-state.ts      → InstanceState
  - bootstrap-runtime.ts   → BootstrapRuntime
  - instance-ref.ts        → InstanceRef / WorkspaceRef
  - instance-registry.ts   → InstanceRegistry (disposers)
  - runtime.ts             → Runtime
  - logger.ts              → EffectLogger
  - observability.ts       → Observability
  - bridge.ts              → EffectBridge
  - cross-spawn-spawner.ts → CrossSpawnSpawner
  - runner.ts              → Runner
  - run-service.ts         → RunService
  - app-runtime.ts         → AppRuntime
  - memo-map.ts            → MemoMap
"""

from __future__ import annotations

import asyncio
import enum
import logging
import os
import platform
import signal
import subprocess
import sys
import threading
import time
import uuid
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Generic,
    NamedTuple,
    Optional,
    TypeVar,
    cast,
    overload,
)

T = TypeVar("T")
E = TypeVar("E", bound=Exception)
A = TypeVar("A")
B = TypeVar("B")
R_co = TypeVar("R_co", covariant=True)

# =============================================================================
# 基础 Effect 类型 — node.ts / temporary.ts
# =============================================================================


class EffectResult(Generic[T]):
    """操作结果容器 (对应 Effect-TS's Exit)"""

    def __init__(self, value: T | None = None, error: Exception | None = None):
        self.value = value
        self.error = error

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def unwrap(self) -> T:
        if self.error:
            raise self.error
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value if self.is_ok else default

    def map(self, fn: Callable[[T], B]) -> EffectResult[B]:
        if self.is_ok:
            return EffectResult(value=fn(self.value))
        return EffectResult(error=self.error)

    def flat_map(self, fn: Callable[[T], EffectResult[B]]) -> EffectResult[B]:
        if self.is_ok:
            return fn(self.value)
        return EffectResult(error=self.error)


class Effect:
    """函数式效果模式 (对应 Effect-TS's Effect module)"""

    @staticmethod
    def succeed(value: T) -> EffectResult[T]:
        return EffectResult(value=value)

    @staticmethod
    def fail(error: Exception) -> EffectResult:
        return EffectResult(error=error)

    @staticmethod
    def from_async(fn: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            try:
                r = fn(*args, **kwargs)
                if hasattr(r, "__await__"):
                    r = await r
                return EffectResult(value=r)
            except Exception as e:
                return EffectResult(error=e)

        return wrapper

    @staticmethod
    def all(results: list[EffectResult]) -> EffectResult[list]:
        values = []
        for r in results:
            if r.is_error:
                return EffectResult(error=r.error)
            values.append(r.value)
        return EffectResult(value=values)

    @staticmethod
    def sync(fn: Callable[[], T]) -> EffectResult[T]:
        try:
            return EffectResult(value=fn())
        except Exception as e:
            return EffectResult(error=e)

    @staticmethod
    def try_except(fn: Callable[[], T], catch: Callable[[Exception], E]) -> EffectResult[T]:
        try:
            return EffectResult(value=fn())
        except Exception as e:
            return EffectResult(error=catch(e))

    @staticmethod
    def async_of(coro: Coroutine[Any, Any, T]) -> Awaitable[EffectResult[T]]:
        async def _run():
            try:
                r = await coro
                return EffectResult(value=r)
            except Exception as e:
                return EffectResult(error=e)

        return _run()

    @staticmethod
    def map(result: EffectResult[T], fn: Callable[[T], B]) -> EffectResult[B]:
        return result.map(fn)

    @staticmethod
    def flat_map(result: EffectResult[T], fn: Callable[[T], EffectResult[B]]) -> EffectResult[B]:
        return result.flat_map(fn)


class Option:
    """可选值模式 (对应 Effect-TS's Option)"""

    @staticmethod
    def some(value: T) -> T | None:
        return value

    @staticmethod
    def none() -> None:
        return None

    @staticmethod
    def is_some(value: Any) -> bool:
        return value is not None

    @staticmethod
    def is_none(value: Any) -> bool:
        return value is None

    @staticmethod
    def get_or(value: T | None, default: T) -> T:
        return value if value is not None else default


class NodeInfo:
    """运行时环境信息 (对应 node.ts)"""

    @property
    def version(self) -> str:
        return f"python {sys.version.split()[0]}"

    @property
    def platform(self) -> str:
        return platform.system().lower()

    @property
    def arch(self) -> str:
        return platform.machine()


node_info = NodeInfo()


# =============================================================================
# instance-ref.ts — 实例引用 / 工作区引用 (Context Reference 等价)
# =============================================================================

# 全局状态: 用于在当前上下文中广播 instance / workspace
_current_instance: threading.local = threading.local()
_current_workspace: threading.local = threading.local()


class InstanceRef:
    """实例引用 — 类似 Effect-TS Context.Reference<InstanceContext>"""

    @staticmethod
    def get() -> Any | None:
        return getattr(_current_instance, "value", None)

    @staticmethod
    def set(value: Any) -> None:
        _current_instance.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_instance, "value"):
            del _current_instance.value


class WorkspaceRef:
    """工作区引用 — 类似 Effect-TS Context.Reference<WorkspaceID>"""

    @staticmethod
    def get() -> str | None:
        return getattr(_current_workspace, "value", None)

    @staticmethod
    def set(value: str) -> None:
        _current_workspace.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_workspace, "value"):
            del _current_workspace.value


# =============================================================================
# instance-registry.ts — 实例处置器注册表
# =============================================================================


class Disposer(NamedTuple):
    fn: Callable[[str], Awaitable[None]]
    phase: str  # "normal" | "late"


_instance_disposers: set[Disposer] = set()
_disposers_lock = threading.Lock()


def register_disposer(
    fn: Callable[[str], Awaitable[None]],
    phase: str = "normal",
) -> Callable[[], None]:
    """注册一个实例释放回调"""
    entry = Disposer(fn=fn, phase=phase)
    with _disposers_lock:
        _instance_disposers.add(entry)

    def unregister() -> None:
        with _disposers_lock:
            _instance_disposers.discard(entry)

    return unregister


async def dispose_instance(directory: str) -> None:
    """释放指定目录下的所有实例资源"""
    normal: list[Disposer] = []
    late: list[Disposer] = []
    with _disposers_lock:
        for d in _instance_disposers:
            if d.phase == "late":
                late.append(d)
            else:
                normal.append(d)

    # 先 normal, 再 late
    results_normal = await asyncio.gather(
        *[d.fn(directory) for d in normal], return_exceptions=True
    )
    results_late = await asyncio.gather(
        *[d.fn(directory) for d in late], return_exceptions=True
    )
    # 静默吞掉所有异常 (Promise.allSettled 语义)
    for r in results_normal + results_late:
        if isinstance(r, Exception):
            logging.getLogger("effect.dispose").warning(
                "dispose_instance error: %s", r
            )


# =============================================================================
# instance-state.ts — 实例状态管理 (ScopedCache 等价)
# =============================================================================


class InstanceState(Generic[T]):
    """
    实例状态 — 基于目录的缓存管理器 (对应 instance-state.ts)
    类似于 Effect-TS ScopedCache<string, A>
    """

    def __init__(
        self,
        init: Callable[[Any], T | Awaitable[T]],
        phase: str = "normal",
    ):
        self._init = init
        self._cache: dict[str, T] = {}
        self._lock = asyncio.Lock()
        self._off = register_disposer(
            lambda d: self._invalidate(d), phase=phase
        )

    async def _invalidate(self, directory: str) -> None:
        async with self._lock:
            self._cache.pop(directory, None)

    async def get(self, ctx: Any = None) -> T:
        dir_key = str(ctx) if ctx is not None else "default"
        async with self._lock:
            if dir_key in self._cache:
                return self._cache[dir_key]
            value = self._init(ctx)
            if hasattr(value, "__await__"):
                value = await value  # type: ignore
            self._cache[dir_key] = value  # type: ignore
            return self._cache[dir_key]  # type: ignore

    async def has(self, ctx: Any = None) -> bool:
        dir_key = str(ctx) if ctx is not None else "default"
        async with self._lock:
            return dir_key in self._cache

    async def invalidate(self, ctx: Any = None) -> None:
        dir_key = str(ctx) if ctx is not None else "default"
        await self._invalidate(dir_key)

    @staticmethod
    def make(
        init: Callable[[Any], T | Awaitable[T]],
        phase: str = "normal",
    ) -> InstanceState[T]:
        return InstanceState(init, phase=phase)

    @staticmethod
    def use(state: InstanceState[T], select: Callable[[T], B], ctx: Any = None) -> Awaitable[B]:
        async def _use() -> B:
            value = await state.get(ctx)
            return select(value)
        return _use()


# =============================================================================
# memo-map.ts — Layer 记忆映射
# =============================================================================


class MemoMap:
    """Layer 记忆映射 (对应 Layer.makeMemoMapUnsafe)"""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: str, factory: Callable[[], Any]) -> Any:
        with self._lock:
            if key not in self._cache:
                self._cache[key] = factory()
            return self._cache[key]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


memo_map = MemoMap()


# =============================================================================
# logger.ts — 效果日志器
# =============================================================================

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


# =============================================================================
# observability.ts — 可观测性 (OpenTelemetry 等价)
# =============================================================================


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


# =============================================================================
# runner.ts — 运行状态机
# =============================================================================


class RunnerTag(enum.Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    SHELL = "Shell"
    SHELL_THEN_RUN = "ShellThenRun"


class RunnerCancelled(Exception):
    """运行器被取消"""


@dataclass
class RunHandle(Generic[A, E]):
    id: int
    done: asyncio.Event
    result: Any = None
    error: Optional[Exception] = None
    task: asyncio.Task | None = None


@dataclass
class ShellHandle(Generic[A, E]):
    id: int
    task: asyncio.Task


@dataclass
class PendingHandle(Generic[A, E]):
    id: int
    done: asyncio.Event
    work: Callable[[], Awaitable[A]]
    result: Any = None
    error: Optional[Exception] = None


class RunnerState(NamedTuple):
    tag: RunnerTag
    run: RunHandle | None = None
    shell: ShellHandle | None = None
    pending: PendingHandle | None = None


class Runner(Generic[A, E]):
    """
    运行状态机 — 对应 runner.ts
    支持 Idle → Running → Shell → ShellThenRun 状态转换
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop | None = None,
        on_idle: Callable[[], Awaitable[None]] | None = None,
        on_busy: Callable[[], Awaitable[None]] | None = None,
        on_interrupt: Callable[[], Awaitable[A]] | None = None,
        label: str = "",
    ):
        self._state = RunnerState(tag=RunnerTag.IDLE)
        self._lock = asyncio.Lock()
        self._ids = 0
        self._loop_provided = loop
        self._on_idle = on_idle
        self._on_busy = on_busy
        self._on_interrupt = on_interrupt
        self._label = label

    @property
    def _loop(self) -> asyncio.AbstractEventLoop:
        return self._loop_provided or asyncio.get_running_loop()

    @property
    def busy(self) -> bool:
        return self._state.tag != RunnerTag.IDLE

    def _next_id(self) -> int:
        self._ids += 1
        return self._ids

    async def _finish_run(self, run_id: int, done: asyncio.Event) -> None:
        async with self._lock:
            st = self._state
            if st.tag == RunnerTag.RUNNING and st.run and st.run.id == run_id:
                if self._on_idle:
                    await self._on_idle()
                done.set()
                self._state = RunnerState(tag=RunnerTag.IDLE)

    async def _finish_shell(self, shell_id: int) -> None:
        async with self._lock:
            st = self._state
            if st.tag == RunnerTag.SHELL and st.shell and st.shell.id == shell_id:
                if self._on_idle:
                    await self._on_idle()
                self._state = RunnerState(tag=RunnerTag.IDLE)
            elif (
                st.tag == RunnerTag.SHELL_THEN_RUN
                and st.shell
                and st.shell.id == shell_id
            ):
                # transition: Shell -> Running
                pending = st.pending
                if pending:
                    task = asyncio.ensure_future(self._run_work(pending.work, pending.done, pending.id))
                    run = RunHandle(
                        id=pending.id,
                        done=pending.done,
                        task=task,
                    )
                    self._state = RunnerState(
                        tag=RunnerTag.RUNNING, run=run
                    )

    async def _run_work(self, work: Callable[[], Awaitable[A]], done: asyncio.Event, run_id: int) -> None:
        try:
            result = await work()
            async with self._lock:
                st = self._state
                if st.tag == RunnerTag.RUNNING and st.run and st.run.id == run_id:
                    st.run.result = result
                    st.run.done.set()
                    if self._on_idle:
                        await self._on_idle()
                    self._state = RunnerState(tag=RunnerTag.IDLE)
        except RunnerCancelled:
            done.set()
        except Exception as e:
            async with self._lock:
                st = self._state
                if st.tag == RunnerTag.RUNNING and st.run and st.run.id == run_id:
                    st.run.error = e
                    st.run.done.set()
                    if self._on_idle:
                        await self._on_idle()
                    self._state = RunnerState(tag=RunnerTag.IDLE)

    async def ensure_running(self, work: Callable[[], Awaitable[A]]) -> A:
        """确保有一个运行中的任务"""
        async with self._lock:
            st = self._state
            if st.tag == RunnerTag.RUNNING or st.tag == RunnerTag.SHELL_THEN_RUN:
                # wait for existing run
                done = st.run.done if st.run else (st.pending.done if st.pending else asyncio.Event())
                # release lock before await
                self._lock.release()
                try:
                    await done.wait()
                finally:
                    await self._lock.acquire()
                if st.tag == RunnerTag.RUNNING and st.run:
                    if st.run.error:
                        raise st.run.error
                    return st.run.result
                raise RunnerCancelled()

            elif st.tag == RunnerTag.SHELL:
                pending_id = self._next_id()
                done = asyncio.Event()
                pending = PendingHandle(
                    id=pending_id,
                    done=done,
                    work=work,
                )
                self._state = RunnerState(
                    tag=RunnerTag.SHELL_THEN_RUN,
                    shell=st.shell,
                    pending=pending,
                )
                self._lock.release()
                try:
                    await done.wait()
                finally:
                    await self._lock.acquire()
                if pending.error:
                    raise pending.error
                return pending.result

            else:  # IDLE
                run_id = self._next_id()
                done = asyncio.Event()
                task = asyncio.ensure_future(self._run_work(work, done, run_id))
                run = RunHandle(id=run_id, done=done, task=task)
                self._state = RunnerState(tag=RunnerTag.RUNNING, run=run)
                self._lock.release()
                try:
                    await done.wait()
                finally:
                    await self._lock.acquire()
                if run.error:
                    raise run.error
                return run.result

    async def start_shell(self, work: Callable[[], Awaitable[A]]) -> A:
        """启动一个 shell 任务"""
        async with self._lock:
            st = self._state
            if st.tag != RunnerTag.IDLE:
                raise RuntimeError("Runner is busy")

            if self._on_busy:
                await self._on_busy()

            shell_id = self._next_id()

            async def _shell_wrapper() -> A:
                try:
                    return await work()
                finally:
                    await self._finish_shell(shell_id)

            task = asyncio.ensure_future(_shell_wrapper())
            shell = ShellHandle(id=shell_id, task=task)
            self._state = RunnerState(tag=RunnerTag.SHELL, shell=shell)
            self._lock.release()
            try:
                result = await task
                return result
            except RunnerCancelled:
                if self._on_interrupt:
                    return await self._on_interrupt()
                raise
            finally:
                await self._lock.acquire()

    async def cancel(self) -> None:
        """取消当前运行"""
        async with self._lock:
            st = self._state
            if st.tag == RunnerTag.IDLE:
                return

            if st.tag == RunnerTag.RUNNING and st.run:
                if st.run.task:
                    st.run.task.cancel()
                st.run.done.set()
                if self._on_idle:
                    await self._on_idle()
                self._state = RunnerState(tag=RunnerTag.IDLE)

            elif st.tag == RunnerTag.SHELL and st.shell:
                if st.shell.task:
                    st.shell.task.cancel()
                if self._on_idle:
                    await self._on_idle()
                self._state = RunnerState(tag=RunnerTag.IDLE)

            elif st.tag == RunnerTag.SHELL_THEN_RUN:
                if st.pending:
                    st.pending.error = RunnerCancelled()
                    st.pending.done.set()
                if st.shell and st.shell.task:
                    st.shell.task.cancel()
                if self._on_idle:
                    await self._on_idle()
                self._state = RunnerState(tag=RunnerTag.IDLE)

    @staticmethod
    def make(
        loop: asyncio.AbstractEventLoop | None = None,
        on_idle: Callable[[], Awaitable[None]] | None = None,
        on_busy: Callable[[], Awaitable[None]] | None = None,
        on_interrupt: Callable[[], Awaitable[A]] | None = None,
        label: str = "",
    ) -> Runner[A, E]:
        return Runner(
            loop=loop,
            on_idle=on_idle,
            on_busy=on_busy,
            on_interrupt=on_interrupt,
            label=label,
        )


# =============================================================================
# bridge.ts — Effect Bridge (上下文恢复)
# =============================================================================


class EffectBridge:
    """
    Effect Bridge — 提供 promise/fork 功能, 自动恢复实例/工作区上下文
    对应 bridge.ts 的 Shape
    """

    def __init__(
        self,
        instance: Any = None,
        workspace: str | None = None,
    ):
        self._instance = instance
        self._workspace = workspace

    def _restore_context(self, fn: Callable[[], R]) -> R:
        """在保存的上下文中执行函数"""
        prev_instance = InstanceRef.get()
        prev_workspace = WorkspaceRef.get()
        try:
            if self._instance is not None:
                InstanceRef.set(self._instance)
            if self._workspace is not None:
                WorkspaceRef.set(self._workspace)
            return fn()
        finally:
            if self._instance is not None:
                InstanceRef.set(prev_instance)
            if self._workspace is not None:
                WorkspaceRef.set(prev_workspace)

    def promise(self, coro_factory: Callable[[], Coroutine[Any, Any, A]]) -> Awaitable[A]:
        """在恢复的上下文中运行协程"""
        return self._restore_context(coro_factory)

    def fork(self, coro_factory: Callable[[], Coroutine[Any, Any, A]]) -> asyncio.Task[A]:
        """在恢复的上下文中派生子任务"""
        coro = self._restore_context(coro_factory)
        return asyncio.ensure_future(coro)

    @staticmethod
    async def make(
        instance: Any = None,
        workspace: str | None = None,
    ) -> EffectBridge:
        return EffectBridge(instance=instance, workspace=workspace)


# =============================================================================
# run-service.ts — 运行时工厂 (attach 模式)
# =============================================================================


def attach_with(
    effect_fn: Callable[..., Any],
    refs: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """
    将 effect 与实例/工作区引用绑定
    对应 run-service.ts 的 attachWith
    """
    refs = refs or {}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        prev_instance = InstanceRef.get()
        prev_workspace = WorkspaceRef.get()
        try:
            if "instance" in refs:
                InstanceRef.set(refs["instance"])
            if "workspace" in refs:
                WorkspaceRef.set(refs["workspace"])
            return effect_fn(*args, **kwargs)
        finally:
            InstanceRef.set(prev_instance)
            WorkspaceRef.set(prev_workspace)

    return wrapper


def attach(effect_fn: Callable[..., Any]) -> Callable[..., Any]:
    """
    自动附加当前实例/工作区引用
    对应 run-service.ts 的 attach
    """
    try:
        instance = InstanceRef.get()
        workspace = WorkspaceRef.get()
        return attach_with(effect_fn, {"instance": instance, "workspace": workspace})
    except Exception:
        return effect_fn


def make_runtime(
    service_name: str,
    layers: list[Any] | None = None,
) -> "Runtime":
    """
    创建运行时 (对应 run-service.ts 的 makeRuntime)
    """
    return Runtime(
        service_name=service_name,
        layers=layers or [],
        memo_map=memo_map,
    )


# =============================================================================
# runtime.ts — 通用运行时 (ManagedRuntime 等价)
# =============================================================================


class Runtime:
    """
    通用运行时 — 对应 runtime.ts 的 makeRuntime
    封装 ManagedRuntime.runSync / runPromise / runFork 等价
    """

    def __init__(
        self,
        service_name: str,
        layers: list[Any] | None = None,
        memo_map: MemoMap | None = None,
    ):
        self._service_name = service_name
        self._layers = layers or []
        self._memo_map = memo_map or MemoMap()
        self._initialized = False

    def _ensure(self) -> None:
        if not self._initialized:
            self._initialized = True

    def run_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        self._ensure()
        return fn(*args, **kwargs)

    def run_promise(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> Awaitable[T]:
        self._ensure()
        return fn(*args, **kwargs)

    def run_fork(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> asyncio.Task[T]:
        self._ensure()
        return asyncio.ensure_future(fn(*args, **kwargs))

    def run_callback(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[T]:
        self._ensure()

        async def _wrapped() -> T:
            try:
                result = await fn(*args, **kwargs)
                if on_done:
                    on_done(result)
                return result
            except Exception as e:
                if on_error:
                    on_error(e)
                raise

        return asyncio.ensure_future(_wrapped())

    def dispose(self) -> None:
        self._initialized = False
        self._memo_map.clear()


# =============================================================================
# cross-spawn-spawner.ts — 子进程生成器
# =============================================================================


class ProcessResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str
    pid: int


class CrossSpawnSpawner:
    """
    子进程生成器 — 对应 cross-spawn-spawner.ts
    使用 Python subprocess 实现跨平台进程生成
    """

    DEFAULT_TIMEOUT: float = 300.0  # 5 分钟

    @staticmethod
    def to_error(err: Any) -> Exception:
        if isinstance(err, Exception):
            return err
        return Exception(str(err))

    @staticmethod
    def to_system_error_tag(err: OSError) -> str:
        errno_map = {
            "ENOENT": "NotFound",
            "EACCES": "PermissionDenied",
            "EEXIST": "AlreadyExists",
            "EISDIR": "BadResource",
            "ENOTDIR": "BadResource",
            "EBUSY": "Busy",
            "ELOOP": "BadResource",
        }
        # Try to find by errno
        import errno as errno_module

        errno_to_tag = {
            errno_module.ENOENT: "NotFound",
            errno_module.EACCES: "PermissionDenied",
            errno_module.EEXIST: "AlreadyExists",
            errno_module.EISDIR: "BadResource",
            errno_module.ENOTDIR: "BadResource",
            errno_module.EBUSY: "Busy",
            errno_module.ELOOP: "BadResource",
        }
        return errno_to_tag.get(err.errno, "Unknown")

    @classmethod
    def spawn(
        cls,
        command: str | list[str],
        args: list[str] | None = None,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        extend_env: bool = True,
        shell: bool = False,
        timeout: float | None = None,
        stdin_data: str | None = None,
        detach: bool = False,
        kill_signal: str = "SIGTERM",
        force_kill_after: float | None = None,
    ) -> ProcessResult:
        """
        同步生成子进程 (对应 spawnCommand)
        """
        if isinstance(command, str):
            cmd = command if shell else [command]
        else:
            cmd = command

        if args and not shell:
            cmd = cmd + args
        elif args and shell:
            cmd = cmd + args

        if extend_env and env:
            merged_env = {**os.environ, **env}
        else:
            merged_env = env

        effective_timeout = timeout or cls.DEFAULT_TIMEOUT

        try:
            proc = subprocess.Popen(
                cmd if not shell else " ".join(cmd) if isinstance(cmd, list) else cmd,
                stdin=subprocess.PIPE if stdin_data is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=merged_env,
                shell=shell,
                preexec_fn=os.setsid if detach and sys.platform != "win32" else None,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                if detach and sys.platform == "win32"
                else 0,
            )
        except OSError as e:
            tag = cls.to_system_error_tag(e)
            raise OSError(f"[{tag}] Failed to spawn: {e}") from e

        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                input=stdin_data.encode("utf-8") if stdin_data else None,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            if force_kill_after:
                proc.kill()
                proc.wait(timeout=10)
            else:
                if sys.platform == "win32":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(getattr(signal, kill_signal, signal.SIGTERM))
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            raise

        return ProcessResult(
            returncode=proc.returncode or 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "",
            stderr=stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "",
            pid=proc.pid or 0,
        )

    @classmethod
    async def spawn_async(
        cls,
        command: str | list[str],
        args: list[str] | None = None,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        extend_env: bool = True,
        shell: bool = False,
        timeout: float | None = None,
        stdin_data: str | None = None,
    ) -> ProcessResult:
        """
        异步生成子进程
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: cls.spawn(
                command,
                args,
                cwd=cwd,
                env=env,
                extend_env=extend_env,
                shell=shell,
                timeout=timeout,
                stdin_data=stdin_data,
            ),
        )

    @classmethod
    def spawn_with_stream(
        cls,
        command: str | list[str],
        args: list[str] | None = None,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdout_callback: Callable[[str], None] | None = None,
        stderr_callback: Callable[[str], None] | None = None,
        shell: bool = False,
        **kwargs: Any,
    ) -> int:
        """
        生成子进程并流式读取输出
        """
        if isinstance(command, str):
            cmd = command if shell else [command]
        else:
            cmd = command

        if args and not shell:
            cmd = cmd + args
        elif args and shell:
            cmd = cmd + args

        if extend_env := kwargs.get("extend_env", True):
            merged_env = {**os.environ, **(env or {})}
        else:
            merged_env = env

        proc = subprocess.Popen(
            cmd if not shell else " ".join(cmd) if isinstance(cmd, list) else cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
            shell=shell,
            bufsize=1,
            universal_newlines=True,
        )

        def _read_stream(stream: Any, callback: Callable[[str], None] | None) -> None:
            for line in stream:
                if callback:
                    callback(line.rstrip("\n"))

        threads = []
        if stdout_callback:
            t = threading.Thread(
                target=_read_stream, args=(proc.stdout, stdout_callback), daemon=True
            )
            t.start()
            threads.append(t)
        if stderr_callback:
            t = threading.Thread(
                target=_read_stream, args=(proc.stderr, stderr_callback), daemon=True
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        proc.wait()
        return proc.returncode or 0


# =============================================================================
# bootstrap-runtime.ts — 启动运行时
# =============================================================================


class BootstrapRuntime:
    """
    启动运行时 — 对应 bootstrap-runtime.ts
    合并所有默认层并创建 ManagedRuntime
    """

    _instance: "BootstrapRuntime | None" = None
    _lock = threading.Lock()

    def __init__(self, layers: list[Any] | None = None):
        self._layers = layers or []
        self._runtime = Runtime(
            service_name="bootstrap",
            layers=self._layers,
            memo_map=memo_map,
        )

    @property
    def runtime(self) -> Runtime:
        return self._runtime

    def run_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        return self._runtime.run_sync(fn, *args, **kwargs)

    def run_promise(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> Awaitable[T]:
        return self._runtime.run_promise(fn, *args, **kwargs)

    def run_fork(
        self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> asyncio.Task[T]:
        return self._runtime.run_fork(fn, *args, **kwargs)

    @classmethod
    def get_instance(cls, layers: list[Any] | None = None) -> BootstrapRuntime:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(layers=layers)
            return cls._instance


# =============================================================================
# app-runtime.ts — 应用运行时
# =============================================================================


class AppRuntime:
    """
    应用运行时 — 对应 app-runtime.ts
    单例模式, 提供全局 runSync / runPromise / runFork 入口
    """

    _instance: "AppRuntime | None" = None
    _lock = threading.Lock()

    def __init__(self, layers: list[Any] | None = None):
        self._layers = layers or []
        # 使用 Observability 层包裹
        self._runtime = Runtime(
            service_name="app",
            layers=[Observability.layer(el) for el in self._layers],
            memo_map=memo_map,
        )

    def run_sync(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        wrapped = attach(fn)
        return self._runtime.run_sync(wrapped, *args, **kwargs)

    def run_promise(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> Awaitable[T]:
        wrapped = attach(fn)
        return self._runtime.run_promise(wrapped, *args, **kwargs)

    def run_promise_exit(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        options: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> Awaitable[T]:
        wrapped = attach(fn)
        return self._runtime.run_promise(wrapped, *args, **kwargs)

    def run_fork(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[T]:
        wrapped = attach(fn)
        return self._runtime.run_fork(wrapped, *args, **kwargs)

    def run_callback(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[T]:
        wrapped = attach(fn)
        return self._runtime.run_callback(wrapped, on_done, on_error, *args, **kwargs)

    def dispose(self) -> None:
        self._runtime.dispose()

    @classmethod
    def get_instance(cls, layers: list[Any] | None = None) -> AppRuntime:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(layers=layers)
            return cls._instance


# =============================================================================
# index.ts — 导出所有 effect 模块
# =============================================================================

# 所有模块已通过类定义导出
# 以下为方便使用而提供的别名

InstanceState = InstanceState
EffectBridge = EffectBridge
Runner = Runner
EffectLogger = EffectLogger
EffectLoggerHandle = EffectLoggerHandle
CrossSpawnSpawner = CrossSpawnSpawner
BootstrapRuntime = BootstrapRuntime
AppRuntime = AppRuntime
MemoMap = MemoMap
Runtime = Runtime
ObservabilityConfig = ObservabilityConfig
