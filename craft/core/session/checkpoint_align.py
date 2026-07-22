"""Checkpoint alignment — ported from checkpoint-align.ts."""

from typing import Any


def align_to_non_tool_result_user(
    messages: list[dict[str, Any]],
    idx: int,
) -> int:
    """Walk backwards from `idx` to find the nearest user message not entirely
    composed of tool_result parts. Returns the aligned index."""
    if idx >= len(messages):
        return idx

    for i in range(idx, -1, -1):
        m = messages[i]
        if m.get("info", m).get("role") != "user":
            continue
        parts = m.get("parts", [])
        # empty-parts message treated as valid
        all_tool_result = len(parts) > 0 and all(
            p.get("type") == "tool_result" for p in parts
        )
        if not all_tool_result:
            return i
    return 0
