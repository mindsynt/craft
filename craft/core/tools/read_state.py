"""Read-state assertion — 移植自 packages/opencode/src/tool/read-state.ts

Throws RecoverableError if the given file was not previously read by the
`read` tool in this conversation. Writes/edits to existing files must be
preceded by a Read so the model sees the current contents.
"""

from __future__ import annotations

import os

from .registry import RecoverableError


def _canon(session_cwd: str, path: str) -> str:
    """Normalize a path for comparison (resolve relative paths)."""
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(session_cwd, path))


def assert_file_read(
    session_cwd: str,
    target_path: str,
    tool_id: str,
    messages: list,
) -> None:
    """Assert that the target file was previously read in this conversation.

    Args:
        session_cwd: Session working directory for resolving relative paths.
        target_path: The file path the tool is trying to edit/write.
        tool_id: The tool ID (e.g., "edit", "write", "apply_patch").
        messages: List of conversation messages, each with .parts containing
                  tool call entries.

    Raises:
        RecoverableError: If the file was not previously read.
    """
    target = _canon(session_cwd, target_path)

    for msg in messages:
        for part in getattr(msg, "parts", msg.get("parts", []) if isinstance(msg, dict) else []):
            part_type = part.get("type") if isinstance(part, dict) else getattr(part, "type", None)
            if part_type != "tool":
                continue
            tool_name = part.get("tool") if isinstance(part, dict) else getattr(part, "tool", None)
            if tool_name != "read":
                continue
            state = part.get("state") if isinstance(part, dict) else getattr(part, "state", None)
            if not state:
                continue
            status = state.get("status") if isinstance(state, dict) else getattr(state, "status", None)
            if status != "completed":
                continue
            inp = state.get("input") if isinstance(state, dict) else getattr(state, "input", {})
            if not isinstance(inp, dict):
                continue
            fp = inp.get("file_path")
            if isinstance(fp, str) and _canon(session_cwd, fp) == target:
                return

    raise RecoverableError(
        f"{tool_id}: {target_path} has not been read in this conversation. "
        f"Call the read tool on this file first, then retry."
    )
