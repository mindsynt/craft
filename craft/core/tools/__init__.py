"""工具/Function 系统 — 拆分为包结构

向后兼容: from craft.core.tools import registry 仍然有效
"""

from __future__ import annotations

# Core types and registry
from .registry import (
    ToolSpec,
    ToolResult,
    RecoverableError,
    ToolResultError,
    Tool,
    ToolRegistry,
    registry,
    tool,
)

# Session working directory
from .session_cwd import SessionCwd

# Truncation service
from .truncate import (
    Truncate,
    MAX_TRUNCATE_LINES,
    MAX_TRUNCATE_BYTES,
    TRUNCATION_DIR,
    ERROR_PATTERN,
)

# Helper utilities
from .utils import (
    _resolve_path,
    _file_size_kb,
    _is_binary_file,
    _trim_diff,
)

# Import tool modules and re-export tool functions directly
from .read import read_file, _read_file_with_lines
from .write import write_file
from .edit import edit, multiedit, EDIT_PARAMETERS
from .edit import (
    _normalize_line_endings,
    _detect_line_ending,
    _levenshtein,
    _find_string_fuzzy,
)
from .bash import bash, MAX_BASH_OUTPUT_BYTES, MAX_BASH_OUTPUT_LINES, DEFAULT_BASH_TIMEOUT_MS
from .bash import _parse_bash_command, _is_delete_command
from .glob import glob as glob_fn
from .grep import grep
from .apply_patch import apply_patch
from .change_directory import change_directory
from .notebook_edit import notebook_edit
from .webfetch import webfetch
from .codesearch import codesearch
from .plan import plan_enter, plan_exit
from .question import question
from .session import session, SESSION_PARAMETERS
from .task import task
from .cron import cron
from .workflow import workflow
from .memory import memory
from .history import history
from .skill import skill, skill_search
from .invalid import invalid
from .actor import actor
from .lsp import lsp

# Re-export bash helpers
# Glob re-export as 'glob' to match original name
glob = glob_fn

from .skill_content import render_skill_content
from .read_state import assert_file_read
from .invocation_style import resolve_invocation_style, InvocationStyle
from .bash_token_efficient import clean, clean_bash_output, create_pipeline, default_plugins, make_clean_result
from .shell_tokenize import tokenize, tokenize_safe, Argv, ParseError
from .shell_wrap import shell_wrap
from .fleet import (
    FleetSession, WorktreeEntry, FleetRow, FleetSummary,
    FleetActorInput, assemble_fleet, render_fleet_table,
)
from .memory_path_guard import (
    assert_memory_write_allowed,
    assert_agent_write_sandbox,
)
from .external_directory import (
    assert_external_directory,
    assert_memory_write_allowed as ext_assert_memory_write_allowed,
    assert_agent_write_sandbox as ext_assert_agent_write_sandbox,
    ask_edit_unless_memory,
)

# Import submodules so they're accessible as attributes
from . import read as _read_mod
from . import write as _write_mod
from . import edit as _edit_mod
from . import bash as _bash_mod
from . import glob as _glob_mod
from . import grep as _grep_mod
from . import apply_patch as _apply_patch_mod
from . import change_directory as _cd_mod
from . import notebook_edit as _notebook_mod
from . import webfetch as _webfetch_mod
from . import codesearch as _codesearch_mod
from . import plan as _plan_mod
from . import question as _question_mod
from . import session as _session_mod
from . import task as _task_mod
from . import cron as _cron_mod
from . import workflow as _workflow_mod
from . import memory as _memory_mod
from . import history as _history_mod
from . import skill as _skill_mod
from . import invalid as _invalid_mod
from . import actor as _actor_mod
from . import lsp as _lsp_mod
from . import read_state as _read_state_mod
from . import invocation_style as _invocation_style_mod
from . import bash_token_efficient as _bash_token_efficient_mod
from . import shell_tokenize as _shell_tokenize_mod
from . import shell_wrap as _shell_wrap_mod
from . import skill_content as _skill_content_mod
from . import fleet as _fleet_mod
from . import memory_path_guard as _memory_path_guard_mod
from . import external_directory as _external_directory_mod

__all__ = [
    # Core types
    "ToolSpec", "ToolResult", "RecoverableError", "ToolResultError",
    "Tool", "ToolRegistry", "registry", "tool",
    # SessionCwd
    "SessionCwd",
    # Truncation
    "Truncate", "MAX_TRUNCATE_LINES", "MAX_TRUNCATE_BYTES", "TRUNCATION_DIR", "ERROR_PATTERN",
    # Utils
    "_resolve_path", "_file_size_kb", "_is_binary_file", "_trim_diff",
    # Tool functions
    "read_file", "write_file", "edit", "multiedit", "bash", "glob", "grep",
    "apply_patch", "change_directory", "notebook_edit", "webfetch", "codesearch",
    "plan_enter", "plan_exit", "question", "session", "task", "cron", "workflow",
    "memory", "history", "skill", "skill_search", "invalid", "actor", "lsp",
    # Edit helpers
    "EDIT_PARAMETERS", "_normalize_line_endings", "_detect_line_ending",
    "_levenshtein", "_find_string_fuzzy",
    # Bash constants/helpers
    "MAX_BASH_OUTPUT_BYTES", "MAX_BASH_OUTPUT_LINES", "DEFAULT_BASH_TIMEOUT_MS",
    "_parse_bash_command", "_is_delete_command",
    # Session helpers
    "SESSION_PARAMETERS",
    # Read helpers
    "_read_file_with_lines",
    # New modules
    "assert_file_read",
    "resolve_invocation_style", "InvocationStyle",
    "clean", "clean_bash_output", "create_pipeline", "default_plugins", "make_clean_result",
    "tokenize", "tokenize_safe", "Argv", "ParseError",
    "shell_wrap",
    "render_skill_content",
    "FleetSession", "WorktreeEntry", "FleetRow", "FleetSummary",
    "FleetActorInput", "assemble_fleet", "render_fleet_table",
    "assert_memory_write_allowed", "assert_agent_write_sandbox",
    "assert_external_directory", "ask_edit_unless_memory",
]
