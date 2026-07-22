"""Memory path guard — 移植自 packages/opencode/src/tool/memory-path-guard.ts

Enforces write-safety rules for memory-scoped files. Two policies:
1. For checkpoint-writer subagent: must be in the precise allowlist.
2. For all other agents: cannot write reserved paths.

Also enforces the write sandbox for system agents (dream/distill).
"""

from __future__ import annotations

import os
import re


VALID_SCOPES: tuple[str, ...] = ("global", "projects", "sessions")

# Agents confined to a write sandbox: they may only mutate files under the
# memory tree or the project's .mimocode/ dir.
WRITE_SANDBOXED_AGENTS: frozenset[str] = frozenset({"dream", "distill"})

_TASK_ID_RE = re.compile(r"^T\d+(\.\d+)*$")


def assert_agent_write_sandbox(
    target: str,
    agent_name: str,
    memory_root: str,
    worktree: str,
) -> None:
    """Hard write-boundary for sandboxed system agents (dream/distill).

    Throws ValueError if agent_name is sandboxed and target is neither
    under the memory tree nor under <worktree>/.mimocode/.
    """
    if agent_name not in WRITE_SANDBOXED_AGENTS:
        return

    target = os.path.normpath(target)
    memory_root = os.path.normpath(memory_root)
    dot_dir = os.path.normpath(os.path.join(worktree, ".mimocode"))

    if _path_contains(memory_root, target) or _path_contains(dot_dir, target):
        return

    raise ValueError(
        f"Agent '{agent_name}' may only write under the memory tree or {dot_dir}.\n"
        f"  memory: {memory_root}\n"
        f"  config: {dot_dir}\n"
        f"You attempted: {target}."
    )


def _path_contains(root: str, child: str) -> bool:
    """True when `child` is `root` itself or nested under it."""
    normalized_root = root[:-1] if root.endswith(os.sep) else root
    return child == normalized_root or child.startswith(normalized_root + os.sep)


def _is_checkpoint_writer_allowed(parts: list[str]) -> bool:
    """Check if relative path parts are in the checkpoint-writer allowlist."""
    if len(parts) < 3:
        return False

    if parts[0] == "projects":
        if len(parts) != 3:
            return False
        file = parts[2]
        if not file.endswith(".md"):
            return False
        lower = file.lower()
        return lower == "memory.md" or lower.startswith("memory-")

    if parts[0] == "sessions":
        rest = parts[2:]
        if len(rest) == 1:
            file = rest[0]
            if not file.endswith(".md"):
                return False
            return file in ("checkpoint.md", "notes.md") or file.startswith("checkpoint-")
        if len(rest) == 3 and rest[0] == "tasks":
            return bool(_TASK_ID_RE.match(rest[1])) and rest[2].endswith(".md")
        return False

    return False


def _is_reserved_for_checkpoint_writer(parts: list[str]) -> bool:
    """Paths under <sid>/tasks/ are reserved for the checkpoint-writer."""
    if parts[0] != "sessions" or len(parts) < 4:
        return False
    return parts[2] == "tasks"


def format_main_agent_help(memory_file: str, notes_file: str, target: str) -> str:
    """Format the multi-line 'where to write memory' hint."""
    return (
        f"Memory writes go under <memoryRoot>/<scope>/<scope_id>/<key>.md "
        f"(scope: global | projects | sessions). You attempted: {target}.\n\n"
        f"Canonical main-agent paths (copy verbatim):\n"
        f"  {memory_file}\n"
        f"    Edit ## Rules / ## Architecture decisions / ## Discovered durable knowledge.\n"
        f"  {notes_file}\n"
        f"    Append `## [turn N · ISO-Z]` entries for free-form scratch.\n\n"
        f"Other free-form <key>.md under a valid scope dir are also allowed.\n"
        f"checkpoint.md, task progress, and memory-/checkpoint-<topic>.md spillovers "
        f"are checkpoint-writer's domain."
    )


def assert_memory_write_allowed(
    target: str,
    agent_name: str,
    memory_root: str,
    project_id: str,
    session_id: str,
    task_id: str | None = None,
) -> None:
    """Throws ValueError if the target write would violate memory-scope rules.

    Two policies:
    - For checkpoint-writer subagent: must be in the precise allowlist.
    - For all other agents: cannot write reserved paths.
    """
    memory_file = os.path.join(memory_root, "projects", project_id, "MEMORY.md")
    notes_file = os.path.join(memory_root, "sessions", session_id, "notes.md")
    checkpoint_file = os.path.join(memory_root, "sessions", session_id, "checkpoint.md")
    task_mem_dir = os.path.join(memory_root, "sessions", session_id, "tasks")

    normalized_root = memory_root[:-1] if memory_root.endswith(os.sep) else memory_root + os.sep
    if not target.startswith(normalized_root):
        return

    rel = os.path.relpath(target, memory_root)
    parts = rel.split(os.sep)

    if len(parts) < 2:
        raise ValueError(format_main_agent_help(memory_file, notes_file, target))

    scope = parts[0]
    if scope not in VALID_SCOPES:
        raise ValueError(format_main_agent_help(memory_file, notes_file, target))

    if agent_name == "checkpoint-writer":
        if not _is_checkpoint_writer_allowed(parts):
            raise ValueError(
                f"Path '{rel}' is not in the checkpoint-writer allowlist.\n"
                f"Writer may only write to:\n"
                f"  {memory_file}     — project memory (or memory-<topic>.md spillover)\n"
                f"  {checkpoint_file}  — session checkpoint (or checkpoint-<topic>.md spillover)\n"
                f"  {task_mem_dir}/<task_id>/*.md  — per-task narratives (any .md filename)\n"
                f"You attempted: {target}."
            )
        return

    if _is_reserved_for_checkpoint_writer(parts):
        # Subagent bound to a specific TID may write under ITS OWN tasks/<TID>/ subtree
        if (
            task_id
            and parts[2] == "tasks"
            and parts[3] == task_id
            and len(parts) >= 5
            and parts[-1].endswith(".md")
        ):
            return
        raise ValueError(
            f"Path '{rel}' is reserved for the checkpoint-writer subagent.\n"
            f"Main agent writes to:\n"
            f"  {memory_file}\n"
            f"  {notes_file}\n"
            f"Subagent bound to task <TID> may write to tasks/<TID>/*.md "
            f"(pass task_id when spawning).\n"
            f"You attempted: {target}."
        )
