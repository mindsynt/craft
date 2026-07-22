"""运行状态机 — Runner, RunnerTag, RunnerCancelled"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    NamedTuple,
    Optional,
    TypeVar,
)

A = TypeVar("A")
E = TypeVar("E", bound=Exception)


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


__all__ = [
    "RunnerTag",
    "RunnerCancelled",
    "RunHandle",
    "ShellHandle",
    "PendingHandle",
    "RunnerState",
    "Runner",
]
