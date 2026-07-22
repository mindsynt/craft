"""Main checkpoint module — ported from checkpoint.ts.

Orchestrates checkpoint writing, context rebuilding, boundary computation,
and related session memory operations.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from craft.core.session.checkpoint_paths import (
    checkpoint_path,
    memory_path,
    notes_path,
    meta_dir,
    tasks_dir,
)
from craft.core.session.checkpoint_templates import (
    CHECKPOINT_TEMPLATE,
    MEMORY_TEMPLATE,
    NOTES_TEMPLATE,
    CHECKPOINT_SECTION_BUDGETS,
)
from craft.core.session.checkpoint_validator import _token_estimate as estimate_tokens

TAIL_MIN_TOKENS = 10_000
TAIL_MAX_TOKENS = 20_000
TAIL_MIN_TEXT_BLOCK_MESSAGES = 5

COMPACTABLE_TOOL_NAMES = {
    "read", "bash", "grep", "glob", "webfetch",
    "websearch", "edit", "write", "multiedit",
    "apply_patch", "codesearch",
}


def compute_boundary(
    messages: list[dict[str, Any]],
) -> str:
    """Token-budgeted, role-aware boundary choice for the preserved tail.

    Returns the ID of the FIRST message to preserve (everything strictly before
    this ID is summarized into checkpoint.md).
    """
    if not messages:
        return ""

    # Find last finished assistant index
    last_asst_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        info = messages[i].get("info", messages[i])
        if info.get("role") == "assistant" and info.get("finish") is not None:
            last_asst_idx = i
            break

    if last_asst_idx <= 0:
        idx = last_asst_idx if last_asst_idx >= 0 else 0
        return messages[idx].get("info", messages[idx]).get("id", "")

    # Token estimate per message
    tokens = []
    for m in messages:
        parts = m.get("parts", [])
        t = 0
        for p in parts:
            try:
                import json
                t += estimate_tokens(json.dumps(p, default=str))
            except (TypeError, ValueError):
                t += 1000
        tokens.append(t)

    def has_text_blocks(m):
        parts = m.get("parts", [])
        return any(p.get("type") in ("text", "reasoning") for p in parts)

    # Start at lastAsstIdx - 1
    start_idx = last_asst_idx - 1
    tail_sum = sum(tokens[start_idx:])
    text_block_count = sum(1 for i in range(start_idx, len(messages)) if has_text_blocks(messages[i]))

    # Natural tail already >= cap
    if tail_sum >= TAIL_MAX_TOKENS:
        return messages[start_idx].get("info", messages[start_idx]).get("id", "")

    # Walk backward until both floors met
    while (start_idx > 0
           and tail_sum < TAIL_MAX_TOKENS
           and (tail_sum < TAIL_MIN_TOKENS or text_block_count < TAIL_MIN_TEXT_BLOCK_MESSAGES)):
        start_idx -= 1
        tail_sum += tokens[start_idx]
        if has_text_blocks(messages[start_idx]):
            text_block_count += 1

    return messages[start_idx].get("info", messages[start_idx]).get("id", "")


def ensure_checkpoint_template(checkpoint_file: str) -> bool:
    """Create checkpoint file from template if it doesn't exist."""
    if os.path.exists(checkpoint_file):
        return False
    os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
    with open(checkpoint_file, "w") as f:
        f.write(CHECKPOINT_TEMPLATE)
    return True


def ensure_memory_template(memory_file: str) -> bool:
    """Create memory file from template if it doesn't exist."""
    if os.path.exists(memory_file):
        return False
    os.makedirs(os.path.dirname(memory_file), exist_ok=True)
    with open(memory_file, "w") as f:
        f.write(MEMORY_TEMPLATE)
    return True


def ensure_notes_template(notes_file: str) -> bool:
    """Create notes file from template if it doesn't exist."""
    if os.path.exists(notes_file):
        return False
    os.makedirs(os.path.dirname(notes_file), exist_ok=True)
    with open(notes_file, "w") as f:
        f.write(NOTES_TEMPLATE)
    return True


def render_section_budgets(budgets: dict[str, int]) -> str:
    """Render section budgets as formatted text."""
    if not budgets:
        raise ValueError("CHECKPOINT_SECTION_BUDGETS is empty")
    entries = list(budgets.items())
    cols = 3
    lines = ["Section budgets (~tokens):"]
    for i in range(0, len(entries), cols):
        row = entries[i : i + cols]
        lines.append("   " + "    ".join(f"{k}: {v}" for k, v in row))
    return "\n".join(lines)


def load_latest_checkpoint(session_id: str, data_root: str | None = None) -> str | None:
    """Return the content of the latest checkpoint file, or None."""
    path = checkpoint_path(session_id, data_root)
    try:
        with open(path) as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return None


def has_checkpoint(session_id: str, data_root: str | None = None) -> bool:
    """Check if a checkpoint file exists."""
    return os.path.isfile(checkpoint_path(session_id, data_root))


def has_memory_or_tasks(session_id: str, data_root: str | None = None) -> bool:
    """Check if the session has any memory artifacts."""
    mem_dir = meta_dir(session_id, data_root)
    if os.path.isdir(mem_dir) and os.listdir(mem_dir):
        return True
    task_dir = tasks_dir(session_id, data_root)
    if os.path.isdir(task_dir) and os.listdir(task_dir):
        return True
    return False


def render_rebuild_context(
    session_id: str,
    data_root: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Build the rebuild-time context from checkpoint files."""
    check = load_latest_checkpoint(session_id, data_root)
    if not check:
        return ""

    parts = [
        "<system-reminder>",
        "The conversation context has been rebuilt. Verify the current state",
        "before acting — the checkpoint below captures accumulated knowledge.",
        "</system-reminder>",
        "",
        "## Accumulated learnings (chronological)",
    ]

    # Parse learnings from checkpoint
    check_lines = check.split("\n")
    in_seven = False
    learnings: list[str] = []
    for line in check_lines:
        if line.startswith("## §7"):
            in_seven = True
            continue
        if in_seven and line.startswith("## §"):
            break
        if in_seven:
            stripped = line.strip()
            if stripped and not stripped.startswith("_"):
                learnings.append(line)

    if learnings:
        parts.extend(learnings)
    else:
        parts.append("(no prior learnings)")

    parts.extend([
        "",
        "## Current snapshot (as of latest checkpoint)",
    ])

    # Extract the current work section
    in_five = False
    snapshot: list[str] = []
    for line in check_lines:
        if line.startswith("## §5"):
            in_five = True
            continue
        if in_five and line.startswith("## §"):
            break
        if in_five:
            snapshot.append(line)

    if snapshot:
        parts.extend(snapshot)
    else:
        parts.append("(latest checkpoint has no current work section)")

    return "\n".join(parts)
