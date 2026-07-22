"""
N-gram repetition detection.

Ported from MiMo-Code: session/prompt/text-ngram-detection.ts

Detects repeated phrases in model output using n-gram analysis.
Provides both direct detection functions and a TextNgramMonitor class
for streaming/incremental use.
"""

from __future__ import annotations

import re
from collections import Counter

TEXT_NGRAM_MAX_RECOVERY = 2
"""Maximum number of n-gram recovery attempts before escalation."""


def tokenize_for_ngram(text: str) -> list[str]:
    """Tokenize text for n-gram analysis.

    Lowercases, collapses whitespace, separates CJK characters,
    and splits into tokens.
    """
    normalized = text.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    # Insert spaces around CJK characters (Unicode ranges)
    normalized = re.sub(
        r"([\u3000-\u9fff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef])",
        r" \1 ",
        normalized,
    )
    normalized = normalized.strip()
    return [t for t in normalized.split(" ") if t]


def detect_repeated_ngram(
    tokens: list[str], n: int, threshold: int
) -> bool:
    """Check if any n-gram appears at least `threshold` times.

    Args:
        tokens: Tokenized text.
        n: N-gram size (number of tokens).
        threshold: Minimum count to flag as repeated.

    Returns:
        True if any n-gram meets or exceeds the threshold.
    """
    if len(tokens) < n or threshold < 2:
        return False
    counts: Counter[str] = Counter()
    for i in range(len(tokens) - n + 1):
        gram = "\0".join(tokens[i : i + n])
        counts[gram] += 1
        if counts[gram] >= threshold:
            return True
    return False


def detect_consecutive_repeat(
    tokens: list[str],
    min_block_size: int,
    threshold: int,
    min_distinct: int = 3,
) -> bool:
    """Detect consecutive repeated blocks in token sequence.

    Checks for period-based repetition: if a block of tokens repeats
    consecutively at a fixed period.

    Args:
        tokens: Tokenized text.
        min_block_size: Minimum block size to consider.
        threshold: Number of repetitions to flag.
        min_distinct: Minimum distinct tokens in a block to qualify.

    Returns:
        True if consecutive repetition is detected.
    """
    if threshold < 2 or len(tokens) < min_block_size * threshold:
        return False
    max_period = len(tokens) // threshold
    for period in range(min_block_size, max_period + 1):
        run = 0
        for i in range(len(tokens) - period - 1):
            if tokens[i] == tokens[i + period]:
                run += 1
                if run >= period * (threshold - 1):
                    block_start = i - run + 1
                    distinct = len(set(tokens[block_start : block_start + period]))
                    if distinct >= min_distinct:
                        return True
            else:
                run = 0
    return False


class TextNgramMonitor:
    """Streaming n-gram monitor that accumulates text and checks for repeats."""

    def __init__(
        self,
        n: int = 3,
        threshold: int = 4,
        window_tokens: int = 200,
        min_distinct: int = 3,
    ):
        self._n = n
        self._threshold = threshold
        self._window_tokens = window_tokens
        self._min_distinct = min_distinct
        self._buffer = ""
        self._tokens: list[str] = []

    def append(self, text: str) -> bool:
        """Append text and check for repetition.

        Returns:
            True if repetition is detected after appending.
        """
        if not text:
            return False
        self._buffer += text
        all_tokens = tokenize_for_ngram(self._buffer)
        if len(all_tokens) > self._window_tokens:
            self._tokens = all_tokens[-self._window_tokens :]
        else:
            self._tokens = all_tokens
        # Trim buffer if too large
        if len(all_tokens) > self._window_tokens * 2:
            self._buffer = " ".join(self._tokens)
        return detect_consecutive_repeat(
            self._tokens, self._n, self._threshold, self._min_distinct
        )

    def reset(self) -> None:
        """Reset the monitor state."""
        self._buffer = ""
        self._tokens = []

    @property
    def tokens(self) -> list[str]:
        """Current token window."""
        return self._tokens


def create_text_ngram_monitor(
    n: int = 3,
    threshold: int = 4,
    window_tokens: int = 200,
) -> TextNgramMonitor:
    """Create a TextNgramMonitor with default parameters."""
    return TextNgramMonitor(n=n, threshold=threshold, window_tokens=window_tokens)


def text_ngram_repeat() -> dict:
    """Create a TextNgramRepeat sentinel."""
    return {"_tag": "TextNgramRepeat"}


def is_text_ngram_repeat(value: object) -> bool:
    """Check if a value is a TextNgramRepeat sentinel."""
    return isinstance(value, dict) and value.get("_tag") == "TextNgramRepeat"


TEXT_NGRAM_RECOVERY_REMIND = """<system-reminder>
REPETITION DETECTED: Your recent output contains repeated phrases (sliding n-gram match within your last 200 tokens).

STOP repeating yourself and retry with a different approach:
- Vary your wording and reasoning — do not reuse the same phrases
- If you were about to call a tool, try a different tool or different arguments
- If you are blocked, explain what is blocking you instead of looping

Do NOT output the same phrases again.
</system-reminder>"""

TEXT_NGRAM_RECOVERY_REPLAN = """<system-reminder>
CRITICAL REPETITION: You are STILL repeating phrases after a recovery attempt.

You MUST completely replan before continuing:
1. Abandon your current approach entirely — it is stuck in repetition
2. Write out a NEW plan with different steps and a different strategy
3. State what you were trying to do, why it failed, and how your new plan differs

Do NOT continue the same line of reasoning or reuse the same wording.
</system-reminder>"""
