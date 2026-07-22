"""
运行时 — 原生工作流引擎
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable

from craft.core.workflow.persistence import WorkflowPersistence

logger = logging.getLogger(__name__)


class WorkflowStep:
    def __init__(self, name: str, agent_id: str = "build", task: str = "",
                 depends_on: list[str] | None = None):
        self.id = uuid.uuid4().hex[:8]
        self.name = name
        self.agent_id = agent_id
        self.task = task
        self.depends_on = depends_on or []
        self.status = "pending"
        self.result: Any = None
        self.error: str | None = None


class WorkflowRun:
    def __init__(self, name: str = "workflow"):
        self.id = f"wf_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.steps: list[WorkflowStep] = []
        self.status = "pending"
        self.created_at = time.time()
        self.completed_at: float | None = None

    def add_step(self, step: WorkflowStep):
        self.steps.append(step)

    def ready_steps(self) -> list[WorkflowStep]:
        completed = {s.id for s in self.steps if s.status == "completed"}
        return [s for s in self.steps if s.status == "pending"
                and all(dep in completed for dep in s.depends_on)]


class WorkflowEngine:
    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}
        self.persistence = WorkflowPersistence()
        self._event_handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable):
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def _emit(self, event: str, data: Any):
        for handler in self._event_handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"[WorkflowEngine] event handler error: {e}")

    def create(self, name: str = "workflow") -> WorkflowRun:
        run = WorkflowRun(name)
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    async def execute(self, run_id: str) -> dict:
        run = self._runs.get(run_id)
        if not run:
            return {"error": "未找到工作流"}
        run.status = "running"
        while True:
            ready = run.ready_steps()
            if not ready:
                break

            async def run_step(step: WorkflowStep):
                step.status = "running"
                try:
                    from craft.core.provider import get_provider
                    llm = get_provider()
                    messages = [{"role": "user", "content": step.task}]
                    resp = await llm.chat(messages=messages)
                    step.result = resp.get("content", "")
                    step.status = "completed"
                except Exception as e:
                    step.status = "failed"
                    step.error = str(e)

            await asyncio.gather(*[run_step(s) for s in ready])

        failed = [s for s in run.steps if s.status == "failed"]
        run.status = "failed" if failed else "completed"
        run.completed_at = time.time()
        return {"id": run.id, "status": run.status, "steps": len(run.steps),
                "failed": len(failed), "completed": time.time() - run.created_at}


workflow_engine = WorkflowEngine()
