"""
Empty tool-call loop guard.

Ported from MiMo-Code: session/prompt/empty-step-detection.ts

Detects assistant steps where the model emits a tool call with completely empty
or invalid arguments — no keys, or only keys with null/undefined/empty values.
"""

from __future__ import annotations

from typing import Any

EMPTY_STEP_MAX_RECOVERY = 2
"""Maximum number of empty-step recovery attempts before halting the turn."""

EMPTY_STEP_RECOVERY_REMIND = """<system-reminder>
Your previous tool call had empty or missing arguments — the tool needs real input to make progress.
Retry the call with COMPLETE arguments, or if the tool is not the right next step, answer the user in plain text.
</system-reminder>"""

EMPTY_STEP_RECOVERY_REPLAN = """<system-reminder>
Second empty tool call. Final chance before this turn is halted.
Either issue a tool call with fully-populated arguments, or give a plain-text reply.
Any further empty-argument tool call will terminate this turn.
</system-reminder>"""


def _is_empty_value(value: Any) -> bool:
    """Check if a value is effectively empty."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    # number / boolean → real value
    return False


def _is_empty_input(input_data: dict[str, Any] | None) -> bool:
    """An input dict counts as empty when it has no keys, or every value is empty."""
    if input_data is None:
        return True
    if len(input_data) == 0:
        return True
    return all(_is_empty_value(v) for v in input_data.values())


def is_empty_step(parts: list[dict[str, Any]]) -> bool:
    """Check if an assistant step is an empty tool call.

    Returns True iff the step has one or more client (non-provider-executed)
    tool parts AND every such tool part has empty/invalid input.

    A step with ANY tool part that has real input is NOT empty.
    A step with no client tool part is NOT empty.
    A step with substantive text or reasoning is NOT empty.
    """
    client_tool_parts = [
        p for p in parts
        if p.get("type") == "tool"
        and not p.get("metadata", {}).get("providerExecuted", False)
    ]

    if not client_tool_parts:
        return False

    # Substantive text or reasoning alongside → not empty
    has_substantive_text = any(
        p.get("type") == "text"
        and not p.get("synthetic", False)
        and not p.get("ignored", False)
        and p.get("text", "").strip()
        for p in parts
    )
    if has_substantive_text:
        return False

    has_substantive_reasoning = any(
        p.get("type") == "reasoning"
        and p.get("text", "").strip()
        for p in parts
    )
    if has_substantive_reasoning:
        return False

    # Every client tool part must have empty input
    return all(_is_empty_input(part.get("state", {}).get("input")) for part in client_tool_parts)
