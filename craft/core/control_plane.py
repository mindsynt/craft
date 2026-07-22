"""
控制平面 — 移植自 packages/opencode/src/control-plane/
中央控制器：Agent 生命周期管理、任务分发、状态协调
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


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
