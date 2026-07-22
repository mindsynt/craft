"""Budgeted file reading — ported from budgeted-read.ts.

Reads files with token budgets, truncating when necessary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BudgetedReadResult:
    text: str = ""
    truncated: bool = False
    total_tokens: int = 0


def _token_estimate(text: str) -> int:
    """Rough token estimation (~4 chars/token)."""
    return len(text) // 4


def read_budgeted(
    file_path: str,
    budget_tokens: int,
) -> BudgetedReadResult | None:
    """Read a file with a token budget."""
    try:
        with open(file_path) as f:
            full_text = f.read()
    except (FileNotFoundError, OSError):
        return None

    total_tokens = _token_estimate(full_text)
    if total_tokens <= budget_tokens:
        return BudgetedReadResult(text=full_text, truncated=False, total_tokens=total_tokens)

    ratio = budget_tokens / total_tokens
    truncated_text = full_text[: int(len(full_text) * ratio * 0.95)]
    last_newline = truncated_text.rfind("\n")
    clean = truncated_text[:last_newline] if last_newline > 0 else truncated_text

    hint = (
        f"\n\n⚠️ Truncated at ~{budget_tokens} tokens. "
        f"{file_path} is ~{total_tokens} tokens total. "
        f'Read("{file_path}", offset={len(clean)}) for the rest.'
    )
    return BudgetedReadResult(text=clean + hint, truncated=True, total_tokens=total_tokens)


@dataclass
class _Section:
    header: str = ""
    italic: str = ""
    body: list[str] = field(default_factory=list)
    index_lines: list[str] = field(default_factory=list)


def _parse_sections(text: str) -> tuple[list[str], list[_Section]]:
    preamble: list[str] = []
    sections: list[_Section] = []
    current: _Section | None = None
    italic_seen = False
    import re

    for line in text.split("\n"):
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = _Section(header=line)
            italic_seen = False
            continue
        if current:
            if not italic_seen and line.startswith("_") and line.endswith("_"):
                current.italic = line
                italic_seen = True
                continue
            if re.match(r"^- See \S+\.md \(\d+", line.strip()):
                current.index_lines.append(line)
            current.body.append(line)
        else:
            preamble.append(line)
    if current:
        sections.append(current)
    return preamble, sections


def read_budgeted_section_aware(
    file_path: str,
    budget_tokens: int,
) -> BudgetedReadResult | None:
    """Read a file with section-aware token budget truncation."""
    try:
        with open(file_path) as f:
            full_text = f.read()
    except (FileNotFoundError, OSError):
        return None

    total_tokens = _token_estimate(full_text)
    if total_tokens <= budget_tokens:
        return BudgetedReadResult(text=full_text, truncated=False, total_tokens=total_tokens)

    preamble, sections = _parse_sections(full_text)
    header_only_tokens = _token_estimate(
        "\n".join(
            preamble
            + [line for s in sections for line in [s.header, s.italic] + s.index_lines]
        )
    )

    if header_only_tokens >= budget_tokens:
        skeleton_lines = preamble
        for s in sections:
            skeleton_lines.extend([s.header, s.italic] + s.index_lines + [""])
        skeleton = "\n".join(skeleton_lines)
        hint = (
            f"\n\n⚠️ File extremely large ({total_tokens} tokens vs budget {budget_tokens}). "
            "Only structure shown.\n"
            f'   Read("{file_path}") for full content.'
        )
        return BudgetedReadResult(text=skeleton + hint, truncated=True, total_tokens=total_tokens)

    out: list[str] = list(preamble)
    used = _token_estimate("\n".join(out))

    for sec in sections:
        header_block = "\n".join([sec.header, sec.italic] + sec.index_lines)
        used += _token_estimate(header_block)
        out.extend([sec.header, sec.italic] + sec.index_lines)

        full_body = "\n".join(l for l in sec.body if l not in sec.index_lines)
        body_tokens = _token_estimate(full_body)
        if used + body_tokens <= budget_tokens:
            out.append(full_body)
            used += body_tokens
        else:
            remaining = budget_tokens - used
            if remaining > 50:
                cut_len = int(len(full_body) * (remaining / body_tokens) * 0.95)
                out.append(full_body[:cut_len])
                used += remaining
        out.append("")

    hint = (
        f"\n\n⚠️ Truncated at ~{budget_tokens} tokens. "
        f"{file_path} is ~{total_tokens} tokens total. "
        f'Read("{file_path}") for full content.'
    )
    return BudgetedReadResult(text="\n".join(out) + hint, truncated=True, total_tokens=total_tokens)
