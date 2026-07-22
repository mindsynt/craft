"""Session summary — ported from summary.ts.

Computes file diffs between snapshots and maintains summary state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileDiff:
    file: str = ""
    additions: int = 0
    deletions: int = 0


@dataclass
class SessionSummaryInfo:
    additions: int = 0
    deletions: int = 0
    files: int = 0


class SummaryManager:
    """Manages session summary state."""

    def __init__(self):
        self._summaries: dict[str, SessionSummaryInfo] = {}
        self._diffs: dict[str, list[FileDiff]] = {}

    def set_summary(self, session_id: str, summary: SessionSummaryInfo) -> None:
        self._summaries[session_id] = summary

    def get_summary(self, session_id: str) -> SessionSummaryInfo | None:
        return self._summaries.get(session_id)

    def set_diffs(self, session_id: str, diffs: list[FileDiff]) -> None:
        self._diffs[session_id] = diffs

    def get_diffs(self, session_id: str) -> list[FileDiff]:
        return self._diffs.get(session_id, [])

    def delete_session(self, session_id: str) -> None:
        self._summaries.pop(session_id, None)
        self._diffs.pop(session_id, None)


summary_manager = SummaryManager()


def unquote_git_path(input_str: str) -> str:
    """Unquote a Git-quoted path (handle octal escapes)."""
    if not input_str.startswith('"'):
        return input_str
    if not input_str.endswith('"'):
        return input_str
    body = input_str[1:-1]
    result = bytearray()
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            result.append(ord(c))
            i += 1
            continue
        if i + 1 >= len(body):
            result.append(ord("\\"))
            i += 1
            continue
        next_c = body[i + 1]
        if "0" <= next_c <= "7":
            import re
            chunk = body[i + 1 : i + 4]
            m = re.match(r"^[0-7]{1,3}", chunk)
            if m:
                result.append(int(m.group(0), 8))
                i += 1 + len(m.group(0))
                continue
        escape_map = {
            "n": "\n", "r": "\r", "t": "\t",
            "b": "\b", "f": "\f", "v": "\v",
            "\\": "\\", '"': '"',
        }
        result.append(ord(escape_map.get(next_c, next_c)))
        i += 2
    return result.decode("utf-8", errors="replace")
