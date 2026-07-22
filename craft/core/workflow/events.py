"""
事件 — 移植自 packages/opencode/src/workflow/events.ts
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowPhaseEvent:
    session_id: str = ""
    run_id: str = ""
    title: str = ""


@dataclass
class WorkflowLogEvent:
    session_id: str = ""
    run_id: str = ""
    message: str = ""


@dataclass
class WorkflowStartedEvent:
    session_id: str = ""
    run_id: str = ""
    name: str = ""


@dataclass
class WorkflowFinishedEvent:
    session_id: str = ""
    run_id: str = ""
    status: str = ""  # "completed" | "failed" | "cancelled"
    error: str | None = None


@dataclass
class WorkflowAgentFailedEvent:
    session_id: str = ""
    run_id: str = ""
    actor_id: str | None = None
    agent_type: str = ""
    label: str | None = None
    phase: str | None = None
    reason: str = ""  # "over-cap" | "spawn-reject" | "timeout" | "actor-error" | "no-deliverable"
    error_message: str | None = None


@dataclass
class WorkflowChildFailedEvent:
    session_id: str = ""
    run_id: str = ""
    child_run_id: str = ""
    name: str = ""
    status: str = ""  # "failed" | "cancelled"
    error: str | None = None
