"""Last message info classification for checkpoint rebuild context.

移植自 MiMo-Code packages/opencode/src/session/last-message-info.ts
"""

from __future__ import annotations

from typing import Any, Literal


def compute_last_message_info(
    msgs: list[dict[str, Any]],
) -> dict[str, str] | None:
    """Inspect the last element of a message array and return a classification.

    - assistant with finish="tool-calls" → mid-loop autonomous
    - assistant with any other finish     → completed naturally
    - tool                                → tool result pending
    - user                                → awaiting assistant response

    Returns None for an empty list.
    """
    if not msgs:
        return None
    last = msgs[-1]
    role = last.get("role", "")
    if role == "assistant":
        finish = last.get("finish", "")
        return {
            "role": "assistant",
            "finish": "tool-calls" if finish == "tool-calls" else "stop",
        }
    if role == "tool":
        return {"role": "tool"}
    return {"role": "user"}
