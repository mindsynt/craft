"""Checkpoint validator — ported from checkpoint-validator.ts."""

import re
from typing import Literal

from craft.core.session.checkpoint_templates import (
    CHECKPOINT_SECTION_BUDGETS,
    MEMORY_SECTION_BUDGETS,
)

ValidationRule = Literal[
    "topic-missing",
    "topic-too-long",
    "topic-anti-pattern-checkpoint-header",
    "subsection-missing",
    "subsection-out-of-order",
    "discovered-duplicate-title",
    "discovered-missing-why",
    "discovered-missing-how-to-apply",
    "next-filler",
    "directive-not-revised",
    "meta-malformed-json",
    "budget-exceeded",
    "section-budget-exceeded",
]

TOPIC_MAX_CHARS = 80

SNAPSHOT_REQUIRED_SECTIONS = [
    "### Execution context",
    "### Live resources",
    "### Session metadata",
]

LEARNING_REQUIRED_SECTIONS = [
    "### Discovered",
    "### Dead ends",
]


class Violation(dict):
    """A validation violation."""

    def __init__(self, file: str, rule: ValidationRule, severity: str, detail: str):
        super().__init__(file=file, rule=rule, severity=severity, detail=detail)
        self.file = file
        self.rule = rule
        self.severity = severity
        self.detail = detail


def _token_estimate(text: str) -> int:
    """Rough token estimation (~4 chars/token)."""
    return len(text) // 4


def _check_topic_and_sections(
    body: str,
    filename: str,
    required_sections: list[str],
) -> list[Violation]:
    violations: list[Violation] = []
    lines = body.split("\n")
    first_non_empty = next((l for l in lines if l.strip()), "")

    if re.match(r"^# Checkpoint #\d+", first_non_empty):
        violations.append(Violation(
            file=filename,
            rule="topic-anti-pattern-checkpoint-header",
            severity="error",
            detail=f'First line is "{first_non_empty}". Replace with "Topic: <≤80-char one-line summary>" with NO leading "#".',
        ))

    topic_match = re.search(r"^Topic:\s*(.+?)$", body, re.MULTILINE)
    if not topic_match:
        violations.append(Violation(
            file=filename,
            rule="topic-missing",
            severity="error",
            detail='Missing required first-line "Topic: <summary>". Add it as the first non-blank line.',
        ))
    else:
        topic = topic_match.group(1).strip()
        if len(topic) > TOPIC_MAX_CHARS:
            violations.append(Violation(
                file=filename,
                rule="topic-too-long",
                severity="warn",
                detail=f"Topic line is {len(topic)} chars (limit {TOPIC_MAX_CHARS}). Rewrite shorter.",
            ))

    section_positions = [(s, body.find(s)) for s in required_sections]
    for s, idx in section_positions:
        if idx == -1:
            violations.append(Violation(
                file=filename,
                rule="subsection-missing",
                severity="error",
                detail=f'Missing "{s}" sub-section. Add the header (use "(none)" placeholder if no entries).',
            ))

    present_in_order = [(s, idx) for s, idx in section_positions if idx != -1]
    for i in range(1, len(present_in_order)):
        if present_in_order[i][1] < present_in_order[i - 1][1]:
            violations.append(Violation(
                file=filename,
                rule="subsection-out-of-order",
                severity="error",
                detail=f"Sub-sections must appear in order: {', '.join(required_sections)}.",
            ))
            break

    return violations


def validate_snapshot(body: str, filename: str) -> list[Violation]:
    return _check_topic_and_sections(body, filename, SNAPSHOT_REQUIRED_SECTIONS)


def extract_discovered_entries(body: str) -> list[dict]:
    """Extract discovered entries as list of {title, block}."""
    match = re.search(
        r"^(?:Topic:.*\n+)?### discovered\s*\n([\s\S]*?)(?=\n### |$)",
        body,
        re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return []
    block = match.group(1)
    entries: list[dict] = []
    current: dict | None = None
    for line in block.split("\n"):
        title_match = re.match(r"^- (.+)$", line)
        if title_match:
            if current:
                entries.append({
                    "title": current["title"],
                    "block": "\n".join(current["lines"]),
                })
            current = {"title": title_match.group(1).strip(), "lines": [line]}
        elif current:
            current["lines"].append(line)
    if current:
        entries.append({
            "title": current["title"],
            "block": "\n".join(current["lines"]),
        })
    return entries


def extract_titles_from_learning(md: str) -> list[str]:
    return [e["title"] for e in extract_discovered_entries(md)]


def validate_learning(
    body: str,
    filename: str,
    prior_discovered_titles: set[str],
) -> list[Violation]:
    violations = _check_topic_and_sections(body, filename, LEARNING_REQUIRED_SECTIONS)
    entries = extract_discovered_entries(body)
    for entry in entries:
        if entry["title"] in prior_discovered_titles:
            violations.append(Violation(
                file=filename,
                rule="discovered-duplicate-title",
                severity="error",
                detail=f'Discovered title "{entry["title"]}" duplicates a prior checkpoint\'s title verbatim. Remove this entry or rephrase.',
            ))
        if not re.search(r"^\s*Why:", entry["block"], re.MULTILINE):
            violations.append(Violation(
                file=filename,
                rule="discovered-missing-why",
                severity="warn",
                detail=f'Discovered entry "{entry["title"]}" is missing a "Why:" line.',
            ))
        if not re.search(r"^\s*How to apply:", entry["block"], re.MULTILINE):
            violations.append(Violation(
                file=filename,
                rule="discovered-missing-how-to-apply",
                severity="warn",
                detail=f'Discovered entry "{entry["title"]}" is missing a "How to apply:" line.',
            ))
    return violations


NEXT_FILLER_PATTERNS = [
    re.compile(r"^\s*continue\s*$", re.IGNORECASE),
    re.compile(r"^\s*resume\s*$", re.IGNORECASE),
    re.compile(r"^\s*keep\s+going\s*$", re.IGNORECASE),
    re.compile(r"^\s*finish\s+up\s*$", re.IGNORECASE),
]


def validate_memory(
    body: str,
    expected_revisions: list[dict],
) -> list[Violation]:
    violations: list[Violation] = []
    for rev in expected_revisions:
        expected_text = rev.get("expectedText", rev.get("expected_text", ""))
        if expected_text and expected_text not in body:
            violations.append(Violation(
                file="MEMORY.md",
                rule="directive-not-revised",
                severity="error",
                detail=f'Directive {rev.get("id", "?")} should mention "{expected_text}" per a recent user instruction, but MEMORY.md does not contain that text.',
            ))
    return violations


def validate_progress(body: str, filename: str) -> list[Violation]:
    violations: list[Violation] = []
    next_lines = re.findall(r"^\s*-?\s*Next:\s*(.+)$", body, re.MULTILINE)
    for line in next_lines:
        if any(pat.search(line) for pat in NEXT_FILLER_PATTERNS):
            violations.append(Violation(
                file=filename,
                rule="next-filler",
                severity="warn",
                detail=f'"Next: {line.strip()}" is filler. Replace with a concrete action (function name, file:line, exact command).',
            ))
    return violations


def validate_budget(content: str, budget: int, filename: str) -> list[Violation]:
    tokens = _token_estimate(content)
    if tokens <= budget:
        return []
    return [
        Violation(
            file=filename,
            rule="budget-exceeded",
            severity="extract-required",
            detail=f"{tokens} tokens > {budget} budget",
        ),
    ]


def validate_budget_sections(
    content: str,
    budgets: dict[str, int],
    filename: str,
) -> list[Violation]:
    violations: list[Violation] = []
    section_re = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = [(m.group(1).strip(), m.start()) for m in section_re.finditer(content)]

    for i, (title, start) in enumerate(matches):
        end = matches[i + 1][1] if i + 1 < len(matches) else len(content)
        section_text = content[start:end]
        budget = budgets.get(title)
        if budget is None:
            continue
        tokens = _token_estimate(section_text)
        if tokens > budget:
            violations.append(Violation(
                file=filename,
                rule="section-budget-exceeded",
                severity="extract-required",
                detail=f'section "{title}" is {tokens} tokens (budget {budget})',
            ))
    return violations


def validate_budget_sections_checkpoint(content: str, filename: str = "checkpoint.md") -> list[Violation]:
    return validate_budget_sections(content, CHECKPOINT_SECTION_BUDGETS, filename)


def validate_budget_sections_memory(content: str, filename: str = "MEMORY.md") -> list[Violation]:
    return validate_budget_sections(content, MEMORY_SECTION_BUDGETS, filename)
