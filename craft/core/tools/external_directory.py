"""External directory assertion — 移植自 packages/opencode/src/tool/external-directory.ts

Permission gate for writes outside the project worktree. Ensures the
user is asked before touching paths outside the working directory.

Also provides ``assert_write_allowed`` — the single write-permission gate
for file-mutating tools (edit, write, apply_patch). Runs both
external_directory and memory-path-guard checks.
"""

from __future__ import annotations

import os
from typing import Any


def assert_external_directory(
    target: str | None,
    project_dir: str | None,
    memory_root: str | None = None,
    worktree_root: str | None = None,
    bypass: bool = False,
    kind: str = "file",
    ask_permission_fn=None,
) -> None:
    """Assert that the target path is within the project directory.

    If the target is outside the project directory, prompts the user via
    the ``ask_permission_fn`` callback.

    Args:
        target: The absolute file/directory path.
        project_dir: The project's working directory.
        memory_root: The memory data directory (auto-allowed).
        worktree_root: The worktree data directory (auto-allowed).
        bypass: If True, skip all checks.
        kind: "file" or "directory".
        ask_permission_fn: Async callback to ask user permission.
                           Called as ask_permission_fn(permission, patterns, ...).
    """
    if not target:
        return
    if bypass:
        return
    if not project_dir:
        return

    target = os.path.normpath(target)
    project_dir = os.path.normpath(project_dir)

    # If target is inside project directory, no check needed
    if target.startswith(project_dir + os.sep) or target == project_dir:
        return

    # Memory tree is trusted
    if memory_root and target.startswith(os.path.normpath(memory_root) + os.sep):
        return

    # Worktree root is trusted (orchestrator-created worktrees)
    if worktree_root and target.startswith(os.path.normpath(worktree_root) + os.sep):
        return

    if ask_permission_fn is not None:
        dir_part = target if kind == "directory" else os.path.dirname(target)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(ask_permission_fn(
                    permission="external_directory",
                    patterns=[os.path.join(dir_part, "*")],
                    always=[os.path.join(dir_part, "*")],
                    metadata={"filepath": target, "parentDir": dir_part},
                ))
        except RuntimeError:
            pass


def assert_memory_write_allowed(
    target: str,
    agent_name: str,
    memory_root: str,
    project_id: str,
    session_id: str,
    task_id: str | None = None,
) -> None:
    """Assert that a memory-path write is permitted for the given agent.

    For checkpoint-writer agent: must be in the precise allowlist.
    For all other agents: cannot write reserved paths.

    Non-memory paths pass through unmodified.

    Raises ValueError if the write would violate rules.
    """
    normalized_root = memory_root if memory_root.endswith(os.sep) else memory_root + os.sep
    if not target.startswith(normalized_root):
        return

    rel = os.path.relpath(target, memory_root)
    parts = rel.split(os.sep)

    valid_scopes = {"global", "projects", "sessions"}

    if len(parts) < 2:
        raise ValueError(
            f"Memory writes go under <memoryRoot>/<scope>/<scope_id>/<key>.md "
            f"(scope: {' | '.join(valid_scopes)}). "
            f"You attempted: {target}."
        )

    scope = parts[0]
    if scope not in valid_scopes:
        raise ValueError(
            f"Invalid memory scope '{scope}'. "
            f"Valid scopes: {' | '.join(valid_scopes)}."
        )

    if agent_name == "checkpoint-writer":
        _assert_checkpoint_writer_allowed(parts, target, memory_root, project_id, session_id)
        return

    # Check reserved paths for non-writer agents
    if _is_reserved_for_checkpoint_writer(parts):
        if (
            task_id
            and len(parts) >= 5
            and parts[2] == "tasks"
            and parts[3] == task_id
            and parts[-1].endswith(".md")
        ):
            return
        raise ValueError(
            f"Path '{rel}' is reserved for the checkpoint-writer subagent. "
            f"Main agent writes to: "
            f"  {os.path.join(memory_root, 'projects', project_id, 'MEMORY.md')} | "
            f"  {os.path.join(memory_root, 'sessions', session_id, 'notes.md')}."
        )


def _is_checkpoint_writer_allowed(parts: list[str]) -> bool:
    """Check if path parts are in the checkpoint-writer allowlist."""
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
            import re
            task_id_re = re.compile(r"^T\d+(\.\d+)*$")
            return task_id_re.match(rest[1]) is not None and rest[2].endswith(".md")
        return False

    return False


def _is_reserved_for_checkpoint_writer(parts: list[str]) -> bool:
    """Check if path is reserved for checkpoint-writer."""
    if parts[0] != "sessions" or len(parts) < 4:
        return False
    return parts[2] == "tasks"


def _assert_checkpoint_writer_allowed(
    parts: list[str],
    target: str,
    memory_root: str,
    project_id: str,
    session_id: str,
) -> None:
    """Assert that checkpoint-writer path is in its allowlist."""
    if not _is_checkpoint_writer_allowed(parts):
        memory_file = os.path.join(memory_root, "projects", project_id, "MEMORY.md")
        checkpoint_file = os.path.join(memory_root, "sessions", session_id, "checkpoint.md")
        task_mem_dir = os.path.join(memory_root, "sessions", session_id, "tasks")
        raise ValueError(
            f"Path is not in the checkpoint-writer allowlist.\n"
            f"Writer may only write to:\n"
            f"  {memory_file}     — project memory (or memory-<topic>.md spillover)\n"
            f"  {checkpoint_file}  — session checkpoint (or checkpoint-<topic>.md spillover)\n"
            f"  {task_mem_dir}/<task_id>/*.md  — per-task narratives\n"
            f"You attempted: {target}."
        )


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
    WRITE_SANDBOXED_AGENTS: frozenset[str] = frozenset({"dream", "distill"})

    if agent_name not in WRITE_SANDBOXED_AGENTS:
        return

    target = os.path.normpath(target)
    memory_root = os.path.normpath(memory_root)
    dot_dir = os.path.normpath(os.path.join(worktree, ".mimocode"))

    def _path_contains(root: str, child: str) -> bool:
        normalized_root = root[:-1] if root.endswith(os.sep) else root
        return child == normalized_root or child.startswith(normalized_root + os.sep)

    if _path_contains(memory_root, target) or _path_contains(dot_dir, target):
        return

    raise ValueError(
        f"Agent '{agent_name}' may only write under the memory tree or {dot_dir}.\n"
        f"  memory: {memory_root}\n"
        f"  config: {dot_dir}\n"
        f"You attempted: {target}."
    )


async def ask_edit_unless_memory(
    filepath: str,
    patterns: list[str],
    diff: str,
    memory_root: str,
    ask_permission_fn=None,
    files: Any = None,
) -> None:
    """Perform the per-write `edit` permission ask, except for memory paths.

    The memory tree's authority is memory-path-guard, which already allows
    the checkpoint-writer / task-bound subagent their canonical paths and
    rejects everything else.
    """
    full = os.path.normpath(filepath)
    if memory_root and full.startswith(os.path.normpath(memory_root) + os.sep):
        return

    if ask_permission_fn is not None:
        metadata: dict[str, Any] = {"filepath": full, "diff": diff}
        if files is not None:
            metadata["files"] = files
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(ask_permission_fn(
                    permission="edit",
                    patterns=patterns,
                    always=["*"],
                    metadata=metadata,
                ))
        except RuntimeError:
            pass
