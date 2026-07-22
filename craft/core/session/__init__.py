"""Session system: data models, checkpoint management, operations, and orchestration.

Ported from MiMo-Code's session/ directory (48 TypeScript files).
Keeps existing Session / SessionManager and extends with checkpoints,
operations, message types, processors, and LLM integration.
"""

from craft.core.session._session import Session, SessionManager, sessions

# Schema
from craft.core.session.schema import SessionID, MessageID, PartID

# Message types
from craft.core.session.message import (
    Role, PartType, ToolStateStatus,
    # Parts
    TextPart, ReasoningPart, ToolPart, FilePart,
    StepStartPart, StepFinishPart, SnapshotPart, PatchPart,
    AgentPart, RetryPart, CheckpointPart, SubtaskPart, CompactionPart,
    # Messages
    UserMessage, AssistantMessage, MessageWithParts,
    # Tool states
    ToolStatePending, ToolStateRunning, ToolStateCompleted, ToolStateError,
    # Types
    TimeRange, AssistantTokens, CacheTokens, AssistantCost, AssistantPath,
    UserModel, Provenance,
    OutputFormatText, OutputFormatJsonSchema,
)

# Status
from craft.core.session.status import (
    SessionStatusManager, SessionStatusInfo,
    StatusIdle, StatusRetry, StatusBusy,
    session_status,
)

# Goal
from craft.core.session.goal import (
    GoalManager, Goal, Verdict, goal_manager,
    JUDGE_SYSTEM, judge_user_prompt,
)

# Todo
from craft.core.session.todo import TodoManager, TodoInfo, todo_manager

# Classify
from craft.core.session.classify import classify_assistant_step

# Boundaries
from craft.core.session.boundary import adjust_boundary_for_api_invariants

# Overflow
from craft.core.session.overflow import (
    usable, is_overflow, pressure_level,
    COMPACTION_BUFFER, OUTPUT_CAP,
)

# Retry
from craft.core.session.retry import (
    is_rate_limit_message, is_retryable_transient_error,
    retry_delay, retryable, retry_policy,
    GO_UPSELL_MESSAGE,
)

# Prune
from craft.core.session.prune import (
    default_thresholds_for, parse_threshold, resolve_thresholds,
    PruneState, prune_state,
)

# Revert
from craft.core.session.revert import SessionRevertManager, RevertState, revert_manager

# Summary
from craft.core.session.summary import (
    SummaryManager, SessionSummaryInfo, FileDiff,
    summary_manager, unquote_git_path,
)

# Trajectory
from craft.core.session.trajectory import (
    serialize_part, serialize_trajectory_messages,
    user_query_text, assistant_final_text,
    session_error_text, with_assistant_parts,
)

# Tool attachment
from craft.core.session.tool_attachment import (
    route_tool_attachment, inline_tool_attachment,
    tool_attachment_filename, tool_attachment_placeholder,
)

# Budgeted read
from craft.core.session.budgeted_read import (
    read_budgeted, read_budgeted_section_aware,
    BudgetedReadResult,
)

# Instruction
from craft.core.session.instruction import InstructionManager, instruction_manager

# System
from craft.core.session.system import (
    provider as system_provider,
    build_environment_prompt, build_memory_instructions,
)

# Run state
from craft.core.session.run_state import (
    RunStateManager, RunnerState, BusyError,
    run_state_manager,
)

# Checkpoint paths
from craft.core.session.checkpoint_paths import (
    meta_dir, checkpoint_path, memory_path, notes_path,
    tasks_dir, progress_path, global_memory_path,
    migrate_project_memory,
)

# Checkpoint templates
from craft.core.session.checkpoint_templates import (
    CHECKPOINT_TEMPLATE, MEMORY_TEMPLATE, NOTES_TEMPLATE,
    CHECKPOINT_SECTION_BUDGETS, MEMORY_SECTION_BUDGETS,
)

# Checkpoint context
from craft.core.session.checkpoint_context import (
    CheckpointContext, set_context, get_context,
    remove_context, reset as ctx_reset, size as ctx_size,
)

# Checkpoint validator
from craft.core.session.checkpoint_validator import (
    Violation,
    validate_snapshot, validate_learning, validate_memory,
    validate_progress, validate_budget, validate_budget_sections,
    validate_budget_sections_checkpoint, validate_budget_sections_memory,
    extract_discovered_entries, extract_titles_from_learning,
)

# Checkpoint retry
from craft.core.session.checkpoint_retry import (
    load_prior_discovered_titles,
    run_validators_for_checkpoint,
    run_task_progress_validators,
    quarantine_checkpoint,
    build_reflection_message,
    build_extraction_reflection,
)

# Checkpoint progress reconcile
from craft.core.session.checkpoint_progress_reconcile import (
    parse_written_at, parse_reconciled_map,
    build_progress_diff_items, render_progress_diff_block,
    build_progress_diff,
)

# Checkpoint align
from craft.core.session.checkpoint_align import (
    align_to_non_tool_result_user,
)

# Checkpoint main
from craft.core.session.checkpoint import (
    compute_boundary, ensure_checkpoint_template,
    ensure_memory_template, ensure_notes_template,
    render_section_budgets, load_latest_checkpoint,
    has_checkpoint, has_memory_or_tasks,
    render_rebuild_context,
)

# Processor
from craft.core.session.processor import (
    ProcessorResult, ProposedToolCall, ReplayInput,
    AgentMetrics, TextNgramMonitor, ProcessorContext,
    compute_diff,
)

# LLM
from craft.core.session.llm import LLMService, llm_service

# LLM request prefix
from craft.core.session.llm_request_prefix import (
    build_llm_request_prefix,
)

# Max mode
from craft.core.session.max_mode import (
    Candidate, MaxStepInput,
    DEFAULT_CANDIDATES, MAX_MODE_AGENT,
    render_candidate, parse_judge_index,
    JUDGE_SYSTEM as MAX_MODE_JUDGE_SYSTEM,
)

__all__ = [
    # Original
    "Session",
    "SessionManager",
    "sessions",
    # Schema
    "SessionID",
    "MessageID",
    "PartID",
    # Message types
    "Role",
    "PartType",
    "ToolStateStatus",
    "TextPart",
    "ReasoningPart",
    "ToolPart",
    "FilePart",
    "StepStartPart",
    "StepFinishPart",
    "SnapshotPart",
    "PatchPart",
    "AgentPart",
    "RetryPart",
    "CheckpointPart",
    "SubtaskPart",
    "CompactionPart",
    "UserMessage",
    "AssistantMessage",
    "MessageWithParts",
    "ToolStatePending",
    "ToolStateRunning",
    "ToolStateCompleted",
    "ToolStateError",
    "TimeRange",
    "AssistantTokens",
    "CacheTokens",
    "AssistantCost",
    "AssistantPath",
    "UserModel",
    "Provenance",
    "OutputFormatText",
    "OutputFormatJsonSchema",
    # Status
    "SessionStatusManager",
    "SessionStatusInfo",
    "StatusIdle",
    "StatusRetry",
    "StatusBusy",
    "session_status",
    # Goal
    "GoalManager",
    "Goal",
    "Verdict",
    "goal_manager",
    "JUDGE_SYSTEM",
    "judge_user_prompt",
    # Todo
    "TodoManager",
    "TodoInfo",
    "todo_manager",
    # Classify
    "classify_assistant_step",
    # Boundary
    "adjust_boundary_for_api_invariants",
    # Overflow
    "usable",
    "is_overflow",
    "pressure_level",
    "COMPACTION_BUFFER",
    "OUTPUT_CAP",
    # Retry
    "is_rate_limit_message",
    "is_retryable_transient_error",
    "retry_delay",
    "retryable",
    "retry_policy",
    "GO_UPSELL_MESSAGE",
    # Prune
    "default_thresholds_for",
    "parse_threshold",
    "resolve_thresholds",
    "PruneState",
    "prune_state",
    # Revert
    "SessionRevertManager",
    "RevertState",
    "revert_manager",
    # Summary
    "SummaryManager",
    "SessionSummaryInfo",
    "FileDiff",
    "summary_manager",
    "unquote_git_path",
    # Trajectory
    "serialize_part",
    "serialize_trajectory_messages",
    "user_query_text",
    "assistant_final_text",
    "session_error_text",
    "with_assistant_parts",
    # Tool attachment
    "route_tool_attachment",
    "inline_tool_attachment",
    "tool_attachment_filename",
    "tool_attachment_placeholder",
    # Budgeted read
    "read_budgeted",
    "read_budgeted_section_aware",
    "BudgetedReadResult",
    # Instruction
    "InstructionManager",
    "instruction_manager",
    # System
    "system_provider",
    "build_environment_prompt",
    "build_memory_instructions",
    # Run state
    "RunStateManager",
    "RunnerState",
    "BusyError",
    "run_state_manager",
    # Checkpoint paths
    "meta_dir",
    "checkpoint_path",
    "memory_path",
    "notes_path",
    "tasks_dir",
    "progress_path",
    "global_memory_path",
    "migrate_project_memory",
    # Checkpoint templates
    "CHECKPOINT_TEMPLATE",
    "MEMORY_TEMPLATE",
    "NOTES_TEMPLATE",
    "CHECKPOINT_SECTION_BUDGETS",
    "MEMORY_SECTION_BUDGETS",
    # Checkpoint context
    "CheckpointContext",
    "set_context",
    "get_context",
    "remove_context",
    "ctx_reset",
    "ctx_size",
    # Checkpoint validator
    "Violation",
    "validate_snapshot",
    "validate_learning",
    "validate_memory",
    "validate_progress",
    "validate_budget",
    "validate_budget_sections",
    "validate_budget_sections_checkpoint",
    "validate_budget_sections_memory",
    "extract_discovered_entries",
    "extract_titles_from_learning",
    # Checkpoint retry
    "load_prior_discovered_titles",
    "run_validators_for_checkpoint",
    "run_task_progress_validators",
    "quarantine_checkpoint",
    "build_reflection_message",
    "build_extraction_reflection",
    # Checkpoint progress reconcile
    "parse_written_at",
    "parse_reconciled_map",
    "build_progress_diff_items",
    "render_progress_diff_block",
    "build_progress_diff",
    # Checkpoint align
    "align_to_non_tool_result_user",
    # Checkpoint main
    "compute_boundary",
    "ensure_checkpoint_template",
    "ensure_memory_template",
    "ensure_notes_template",
    "render_section_budgets",
    "load_latest_checkpoint",
    "has_checkpoint",
    "has_memory_or_tasks",
    "render_rebuild_context",
    # Processor
    "ProcessorResult",
    "ProposedToolCall",
    "ReplayInput",
    "AgentMetrics",
    "TextNgramMonitor",
    "ProcessorContext",
    "compute_diff",
    # LLM
    "LLMService",
    "llm_service",
    # LLM request prefix
    "build_llm_request_prefix",
    # Max mode
    "Candidate",
    "MaxStepInput",
    "DEFAULT_CANDIDATES",
    "MAX_MODE_AGENT",
    "render_candidate",
    "parse_judge_index",
    "MAX_MODE_JUDGE_SYSTEM",
]
