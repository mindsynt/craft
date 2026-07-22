"""Boundary adjustment — ported from boundary.ts.

Walk the boundary backward to ensure tool_use/tool_result pairs are not
split across the summary/tail divide.
"""

from typing import Any


def _get_tool_result_ids(msg: dict[str, Any]) -> list[str]:
    content = msg.get("content")
    if not isinstance(content, list):
        return []
    ids: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tid = block.get("tool_use_id")
            if isinstance(tid, str):
                ids.append(tid)
    return ids


def _get_tool_use_ids(msg: dict[str, Any]) -> list[str]:
    content = msg.get("content")
    if not isinstance(content, list):
        return []
    ids: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            bid = block.get("id")
            if isinstance(bid, str):
                ids.append(bid)
    return ids


def adjust_boundary_for_api_invariants(
    messages: list[dict[str, Any]],
    candidate_boundary: int,
) -> int:
    """Adjust boundary to avoid splitting tool_use/tool_result pairs."""
    if candidate_boundary <= 0 or candidate_boundary >= len(messages):
        return candidate_boundary

    idx = candidate_boundary

    # Step 1: tool_use/tool_result pairing
    tail_tool_results: list[str] = []
    tail_tool_uses: set[str] = set()
    for i in range(idx, len(messages)):
        tail_tool_results.extend(_get_tool_result_ids(messages[i]))
        for use_id in _get_tool_use_ids(messages[i]):
            tail_tool_uses.add(use_id)

    orphans = [tid for tid in tail_tool_results if tid not in tail_tool_uses]

    for i in range(idx - 1, -1, -1):
        if not orphans:
            break
        m = messages[i]
        if m.get("role") != "assistant":
            continue
        use_ids = _get_tool_use_ids(m)
        matched = [uid for uid in use_ids if uid in orphans]
        if matched:
            idx = i
            orphans = [oid for oid in orphans if oid not in matched]

    # Step 2: same message.id walk-back (thinking blocks share id with sibling)
    boundary_msg_id = messages[idx].get("id") if idx < len(messages) else None
    if boundary_msg_id:
        for i in range(idx - 1, -1, -1):
            if messages[i].get("id") == boundary_msg_id:
                idx = i
            else:
                break

    return idx
