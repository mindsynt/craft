"""消息提取 — 移植自 extract.ts"""

from __future__ import annotations

import json
from dataclasses import dataclass

KINDS = frozenset({
    "user_text",
    "assistant_text",
    "tool_input",
    "tool_error",
    "reasoning",
    "tool_output",
})

DEFAULT_KINDS = frozenset({
    "user_text",
    "assistant_text",
    "tool_input",
    "tool_error",
})


@dataclass
class Extracted:
    kind: str
    body: str
    tool_name: str | None = None


def extract(
    part_type: str,
    part_state: dict | None,
    part_text: str | None,
    part_tool: str | None,
    message_role: str,
    enabled_kinds: set[str],
) -> Extracted | None:
    """Extract searchable text from a message part.

    Args:
        part_type: 'text', 'reasoning', or 'tool'
        part_state: dict with 'status', 'input', 'output', 'error' keys
        part_text: text content (for text/reasoning parts)
        part_tool: tool name (for tool parts)
        message_role: 'user' or 'assistant'
        enabled_kinds: set of enabled kind strings

    Returns:
        Extracted object or None if the part should not be indexed.
    """
    if part_type == "text":
        kind = "user_text" if message_role == "user" else "assistant_text"
        if kind not in enabled_kinds or not part_text:
            return None
        return Extracted(kind=kind, body=part_text, tool_name=None)

    if part_type == "reasoning":
        if "reasoning" not in enabled_kinds or not part_text:
            return None
        return Extracted(kind="reasoning", body=part_text, tool_name=None)

    if part_type == "tool":
        state = part_state or {}
        status = state.get("status", "")
        if status in ("pending", "running"):
            return None

        if status == "error" and "tool_error" in enabled_kinds:
            return Extracted(
                kind="tool_error",
                body=f"{part_tool} {json.dumps(state.get('input', {}))} {state.get('error', '')}",
                tool_name=part_tool,
            )
        if status == "completed" and "tool_output" in enabled_kinds:
            return Extracted(
                kind="tool_output",
                body=f"{part_tool} {json.dumps(state.get('input', {}))} {json.dumps(state.get('output', ''))}",
                tool_name=part_tool,
            )
        if "tool_input" in enabled_kinds:
            return Extracted(
                kind="tool_input",
                body=f"{part_tool} {json.dumps(state.get('input', {}))}",
                tool_name=part_tool,
            )
        return None

    return None
