"""
工作流 — 移植自 packages/opencode/src/workflow/
工作流脚本执行、步骤管理、元数据解析、内置工作流、持久化
"""

from __future__ import annotations

from craft.core.workflow.meta import (
    META_START_RE_STR,
    ParseResult,
    WorkflowMeta,
    WorkflowPermission,
    WorkflowPhase,
    parse_meta,
)
from craft.core.workflow.workspace import (
    make_file_hooks,
    resolve_in_workspace,
)
from craft.core.workflow.events import (
    WorkflowAgentFailedEvent,
    WorkflowChildFailedEvent,
    WorkflowFinishedEvent,
    WorkflowLogEvent,
    WorkflowPhaseEvent,
    WorkflowStartedEvent,
)
from craft.core.workflow.resolve import (
    META_RE,
    SAFE_NAME_RE,
    is_inline_script,
    resolve_workflow_script,
)
from craft.core.workflow.builtin import (
    BuiltinEntry,
    BuiltinWorkflowRegistry,
    builtin_registry,
)
from craft.core.workflow.runtime_ref import (
    WorkflowRuntimeRef,
)
from craft.core.workflow.persistence import (
    JournalEvent,
    JournalLoad,
    RunSummary,
    WorkflowPersistence,
    journal_key,
    journal_key_base,
)
from craft.core.workflow.runtime import (
    WorkflowEngine,
    WorkflowRun,
    WorkflowStep,
    workflow_engine,
)

__all__ = [
    # meta
    "META_START_RE_STR", "ParseResult", "WorkflowMeta", "WorkflowPermission",
    "WorkflowPhase", "parse_meta",
    # workspace
    "make_file_hooks", "resolve_in_workspace",
    # events
    "WorkflowAgentFailedEvent", "WorkflowChildFailedEvent", "WorkflowFinishedEvent",
    "WorkflowLogEvent", "WorkflowPhaseEvent", "WorkflowStartedEvent",
    # resolve
    "META_RE", "SAFE_NAME_RE", "is_inline_script", "resolve_workflow_script",
    # builtin
    "BuiltinEntry", "BuiltinWorkflowRegistry", "builtin_registry",
    # runtime_ref
    "WorkflowRuntimeRef",
    # persistence
    "JournalEvent", "JournalLoad", "RunSummary", "WorkflowPersistence",
    "journal_key", "journal_key_base",
    # runtime
    "WorkflowEngine", "WorkflowRun", "WorkflowStep", "workflow_engine",
]
