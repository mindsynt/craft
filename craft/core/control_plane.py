"""
控制平面 — 移植自 packages/opencode/src/control-plane/
中央控制器：Agent 生命周期管理、任务分发、状态协调

支持：SSE 流解析、类型系统、工具函数、工作区上下文管理
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Types ─────────────────────────────────────────────────────
# 对应 TS control-plane/types.ts

@dataclass
class WorkspaceInfo:
    """Information about a workspace in the control plane."""
    id: str
    type: str = "local"
    name: str = ""
    branch: str | None = None
    directory: str | None = None
    extra: Any = None
    project_id: str = ""


@dataclass
class Target:
    """A target for workspace adaptors: local directory or remote URL."""
    type: str = "local"
    directory: str = ""
    url: str = ""
    headers: dict[str, str] | None = None


# ── Utility Functions ─────────────────────────────────────────
# 对应 TS control-plane/util.ts

async def wait_for_event(
    timeout: float,
    signal: asyncio.Event | None = None,
    condition_fn: Callable[[Any], bool] | None = None,
) -> None:
    """Wait for a global event matching a condition, with a timeout.

    Args:
        timeout: Maximum time to wait in seconds.
        signal: An optional asyncio.Event that, when set, aborts the wait.
        condition_fn: Optional predicate to filter which events to resolve on.

    Raises:
        TimeoutError: If the timeout expires before the condition is met.
    """
    if signal and signal.is_set():
        raise TimeoutError("Request aborted")

    event_loop = asyncio.get_event_loop()
    fut: asyncio.Future = asyncio.Future()
    handler: Callable | None = None

    def _on_timeout():
        if not fut.done():
            fut.set_exception(TimeoutError("Timed out waiting for event"))

    timeout_handle = event_loop.call_later(timeout, _on_timeout)

    def _on_signal():
        if not fut.done():
            timeout_handle.cancel()
            fut.set_exception(TimeoutError("Request aborted"))

    if signal:
        signal.add_done_callback(lambda _: _on_signal())

    try:
        await fut
    finally:
        timeout_handle.cancel()
        if signal:
            pass  # signal cleanup handled by caller


# ── SSE Parser ────────────────────────────────────────────────
# 对应 TS control-plane/sse.ts

async def parse_sse(
    read_stream: asyncio.StreamReader,
    signal: asyncio.Event,
    on_event: Callable[[Any], None],
):
    """Parse an SSE (Server-Sent Events) stream.

    Reads from the stream, parses the SSE protocol (data:/id:/retry: fields),
    and calls ``on_event`` for each complete event.
    """
    buf = ""
    last_id = ""
    retry = 1000

    async def _read():
        nonlocal buf, last_id, retry
        try:
            while not signal.is_set():
                chunk = await asyncio.wait_for(read_stream.read(4096), timeout=300)
                if not chunk:
                    break

                buf += chunk.decode("utf-8", errors="replace")
                buf = buf.replace("\r\n", "\n").replace("\r", "\n")

                # Split on double newline (event boundary)
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    data_lines: list[str] = []

                    for line in block.split("\n"):
                        if line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                        elif line.startswith("id:"):
                            last_id = line[3:].strip()
                        elif line.startswith("retry:"):
                            try:
                                retry = int(line[6:].strip())
                            except ValueError:
                                pass

                    if data_lines:
                        raw = "\n".join(data_lines)
                        try:
                            on_event(json.loads(raw))
                        except json.JSONDecodeError:
                            on_event({
                                "type": "sse.message",
                                "properties": {
                                    "data": raw,
                                    "id": last_id or None,
                                    "retry": retry,
                                },
                            })
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error("SSE parse error: %s", e)

    await _read()


# ── Workspace Context ─────────────────────────────────────────
# 对应 TS control-plane/workspace-context.ts

_workspace_context: dict[str, Any] = {}
_context_stack: list[dict[str, Any]] = []


class WorkspaceContext:
    """Workspace context manager for providing and consuming workspace IDs.

    Allows setting a workspace context for a block of code and reading it
    from nested call stacks.
    """

    @staticmethod
    def set(**kwargs):
        """Set workspace context values for the current scope."""
        _workspace_context.update(kwargs)
        _context_stack.append(dict(_workspace_context))

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get a workspace context value."""
        return _workspace_context.get(key, default)

    @staticmethod
    def workspace_id() -> str | None:
        """Get the current workspace ID from context."""
        return _workspace_context.get("workspaceID")

    @staticmethod
    def clear():
        """Clear the workspace context."""
        _workspace_context.clear()

    @staticmethod
    def restore():
        """Restore the previous workspace context from the stack."""
        if _context_stack:
            ctx = _context_stack.pop()
            _workspace_context.clear()
            _workspace_context.update(ctx)

    @staticmethod
    async def provide(workspace_id: str, fn: Callable) -> Any:
        """Run a function within a workspace context."""
        previous = dict(_workspace_context)
        _workspace_context["workspaceID"] = workspace_id
        try:
            result = await fn() if asyncio.iscoroutinefunction(fn) else fn()
            return result
        finally:
            _workspace_context.clear()
            _workspace_context.update(previous)


# ── Original ControlPlane (preserved) ────────────────────────

class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    ERROR = "error"


class Task:
    def __init__(self, agent_id: str, goal: str, context: dict | None = None):
        self.id = f"task_{uuid.uuid4().hex[:8]}"
        self.agent_id = agent_id
        self.goal = goal
        self.context = context or {}
        self.status = "pending"
        self.result: Any = None
        self.error: str | None = None
        self.created_at = time.time()
        self.completed_at: float | None = None


class ControlPlane:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._agents: dict[str, AgentStatus] = {}
        self._max_concurrent = 8
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

    def register_agent(self, agent_id: str):
        self._agents[agent_id] = AgentStatus.IDLE

    def unregister_agent(self, agent_id: str):
        self._agents.pop(agent_id, None)

    def agent_status(self, agent_id: str) -> AgentStatus:
        return self._agents.get(agent_id, AgentStatus.IDLE)

    def set_busy(self, agent_id: str):
        self._agents[agent_id] = AgentStatus.BUSY

    def set_idle(self, agent_id: str):
        self._agents[agent_id] = AgentStatus.IDLE

    def create_task(self, agent_id: str, goal: str, context: dict | None = None) -> Task:
        task = Task(agent_id, goal, context)
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: str | None = None, limit: int = 50) -> list[Task]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks[:limit]

    def available_agents(self) -> list[str]:
        return [aid for aid, status in self._agents.items() if status == AgentStatus.IDLE]

    async def execute(self, agent_id: str, goal: str, context: dict | None = None) -> Task:
        task = self.create_task(agent_id, goal, context)
        self.set_busy(agent_id)
        task.status = "running"

        async with self._semaphore:
            try:
                from craft.core.provider import get_provider
                from craft.core.agent import agents

                agent = agents.get(agent_id)
                llm = get_provider()

                messages = [
                    {"role": "system", "content": agent.prompt if agent else "你是一个助手。"},
                    {"role": "user", "content": goal},
                ]
                resp = await llm.chat(messages=messages)
                task.result = resp.get("content", "")
                task.status = "completed"

            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                logger.error(f"[ControlPlane] 任务失败: {goal[:50]}: {e}")

            finally:
                task.completed_at = time.time()
                self.set_idle(agent_id)

        return task


control_plane = ControlPlane()
