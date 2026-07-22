"""
Text loop detection and recovery.

Ported from MiMo-Code: session/prompt/text-loop-recovery.ts

Detects and handles cases where the model outputs identical text repeatedly.
"""

from __future__ import annotations

import re

TEXT_LOOP_BUFFER_SIZE = 5
"""Number of recent outputs to keep in the loop detection buffer."""

TEXT_LOOP_TRIGGER_COUNT = 3
"""Number of identical consecutive outputs that triggers loop detection."""

TEXT_LOOP_MAX_RECOVERY = 2
"""Maximum number of text-loop recovery attempts before escalation."""


def normalize_for_loop_detection(text: str) -> str:
    """Normalize text for loop comparison.

    Trims, lowercases, collapses whitespace, strips common prefixes,
    and truncates to 200 characters.
    """
    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"^(let me |i'll |i will |let's )", "", normalized)
    return normalized[:200]


def detect_text_loop(buffer: list[str], trigger_count: int) -> bool:
    """Check if the buffer contains a loop (trigger_count identical entries).

    Args:
        buffer: List of normalized text entries (most recent last).
        trigger_count: Number of consecutive identical entries to flag.

    Returns:
        True if the last trigger_count entries are all identical.
    """
    if len(buffer) < trigger_count:
        return False
    tail = buffer[-trigger_count:]
    return all(t == tail[0] for t in tail)


RECOVERY_PROMPT_MILD = """<system-reminder>
LOOP DETECTED: Your last several outputs were identical. You are stuck in a repetitive pattern.

STOP what you are doing and take a DIFFERENT approach:
- If you were about to call a tool, try a different tool or different arguments
- If you were planning an action, reconsider and pick an alternative strategy
- If you are blocked, explain what's blocking you and ask the user for help

Do NOT repeat the same text or action again.
</system-reminder>"""

RECOVERY_PROMPT_STRONG = """<system-reminder>
CRITICAL: You are STILL stuck in a loop after a previous recovery attempt.

Your previous approach has failed repeatedly. You MUST:
1. Abandon your current plan entirely
2. State what you were trying to do and why it failed
3. Ask the user for guidance on how to proceed

If you repeat the same output again, the session will be terminated.
</system-reminder>"""
