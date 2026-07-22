"""
持久化 — 移植自 packages/opencode/src/workflow/persistence.ts
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _canonical(value: Any) -> Any:
    """递归排序对象键 — 移植自 persistence.ts canonical"""
    if value is None or not isinstance(value, (dict, list)):
        return value
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return {k: _canonical(value[k]) for k in sorted(value.keys())}


def journal_key_base(prompt: str, opts: dict) -> str:
    """计算 journal key base — 移植自 persistence.ts journalKeyBase"""
    material = _canonical({
        "prompt": prompt,
        "agentType": opts.get("agentType"),
        "model": opts.get("model"),
        "schema": opts.get("schema"),
        "phase": opts.get("phase"),
    })
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def journal_key(prompt: str, opts: dict, occ: int) -> str:
    """计算完整 journal key — 移植自 persistence.ts journalKey"""
    return f"{journal_key_base(prompt, opts)}:{occ}"


@dataclass
class JournalEvent:
    t: str = ""  # "agent" | "log" | "phase"
    key: str | None = None
    result: Any = None
    msg: str | None = None
    title: str | None = None
    pass_num: int = 0


@dataclass
class JournalLoad:
    results: dict = field(default_factory=dict)
    pass_num: int = 1


@dataclass
class RunSummary:
    run_id: str = ""
    session_id: str = ""
    name: str = ""
    status: str = "running"  # "running" | "completed" | "failed" | "cancelled"
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    current_phase: str | None = None
    parent_actor_id: str | None = None
    args: Any = None
    script_sha: str | None = None
    agent_timeout_ms: int | None = None
    error: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


class WorkflowPersistence:
    """工作流持久化 — 移植自 persistence.ts"""

    def __init__(self, data_dir: str | None = None):
        self._data_dir = data_dir or str(Path.home() / ".craft" / "workflow")
        self._runs: dict[str, RunSummary] = {}

    def record_start(self, run_id: str, session_id: str, name: str,
                     parent_actor_id: str | None = None, args: Any = None,
                     script_sha: str | None = None,
                     agent_timeout_ms: int | None = None):
        """记录工作流启动"""
        now = time.time()
        summary = RunSummary(
            run_id=run_id,
            session_id=session_id,
            name=name,
            status="running",
            parent_actor_id=parent_actor_id,
            args=args,
            script_sha=script_sha,
            agent_timeout_ms=agent_timeout_ms,
            created_at=now,
            updated_at=now,
        )
        self._runs[run_id] = summary

    def record_phase(self, run_id: str, phase: str):
        """记录阶段"""
        run = self._runs.get(run_id)
        if run:
            run.current_phase = phase
            run.updated_at = time.time()

    def flush_counters(self, run_id: str, running: int, succeeded: int, failed: int):
        """刷新计数器"""
        run = self._runs.get(run_id)
        if run:
            run.running = running
            run.succeeded = succeeded
            run.failed = failed
            run.updated_at = time.time()

    def record_terminal(self, run_id: str, status: str, error: str | None = None):
        """记录终止状态"""
        run = self._runs.get(run_id)
        if run:
            run.status = status
            run.error = error
            run.updated_at = time.time()

    def list(self, session_id: str | None = None) -> list[RunSummary]:
        """列出工作流"""
        if session_id:
            return [s for s in self._runs.values() if s.session_id == session_id]
        return list(self._runs.values())

    def load(self, run_id: str) -> RunSummary | None:
        """加载工作流"""
        return self._runs.get(run_id)
