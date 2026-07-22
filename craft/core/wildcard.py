"""
Wildcard pattern matching — ported from MiMo-Code packages/opencode/src/util/wildcard.ts

Supports * (match any sequence), ? (match single char), and standard regex escapes.
"""

from __future__ import annotations

import re
import sys
from typing import Any


def _escape_regex(pattern: str) -> str:
    """Escape special regex characters (same as TS: .+^${}()|[]\\)."""
    result = []
    for ch in pattern:
        if ch in ".+^${}()|[\\]":
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


def match(s: str, pattern: str) -> bool:
    """Check if string matches a wildcard pattern.

    - * matches any sequence of characters
    - ? matches any single character
    - On Windows, matching is case-insensitive
    """
    if s:
        s = s.replace("\\", "/")
    if pattern:
        pattern = pattern.replace("\\", "/")

    # Manually escape special regex chars (same as TS version)
    # Then convert wildcards * → .* and ? → .
    escaped = _escape_regex(pattern)
    escaped = escaped.replace("*", ".*")
    escaped = escaped.replace("?", ".")

    # If pattern ends with " *" (space + wildcard), make trailing part optional
    # This allows "ls *" to match both "ls" and "ls -la"
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + "( .*)?"

    flags = re.IGNORECASE if sys.platform == "win32" else 0
    return bool(re.match("^" + escaped + "$", s, flags))


def all(input_str: str, patterns: dict[str, Any]) -> Any:
    """Match input against an ordered dict of patterns, return value of longest/last match.

    Patterns are sorted by key length (ascending) then key text (ascending).
    The *last* matching pattern wins (findLast semantics via continue).
    """
    sorted_items = sorted(patterns.items(), key=lambda kv: (len(kv[0]), kv[0]))
    result = None
    for pattern, value in sorted_items:
        if match(input_str, pattern):
            result = value
    return result


def _match_sequence(items: list[str], patterns: list[str]) -> bool:
    """Match a sequence of items against a sequence of patterns (with * support)."""
    if not patterns:
        return True
    pattern = patterns[0]
    rest = patterns[1:]
    if pattern == "*":
        return _match_sequence(items, rest)
    for i in range(len(items)):
        if match(items[i], pattern) and _match_sequence(items[i + 1 :], rest):
            return True
    return False


def all_structured(input_data: dict[str, Any], patterns: dict[str, Any]) -> Any:
    """Match structured input (head string + tail list) against patterns with split support.

    Like all(), but pattern keys are split on whitespace: the first token
    matches input['head'], and the remaining tokens match input['tail'] as a sequence.
    """
    sorted_items = sorted(patterns.items(), key=lambda kv: (len(kv[0]), kv[0]))
    result = None
    for pattern, value in sorted_items:
        parts = pattern.split()
        if not match(input_data["head"], parts[0]):
            continue
        if len(parts) == 1 or _match_sequence(input_data["tail"], parts[1:]):
            result = value
    return result
