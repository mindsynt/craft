"""Checkpoint retry / validation runner — ported from checkpoint-retry.ts."""

import os

from craft.core.session.checkpoint_paths import (
    checkpoint_path,
    memory_path,
    meta_dir,
)
from craft.core.session.checkpoint_templates import (
    CHECKPOINT_SECTION_BUDGETS,
    MEMORY_SECTION_BUDGETS,
)
from craft.core.session.checkpoint_validator import (
    Violation,
    extract_titles_from_learning,
    validate_budget,
    validate_budget_sections,
    validate_learning,
    validate_memory,
    validate_progress,
    validate_snapshot,
)


def load_prior_discovered_titles(session_id: str, data_root: str | None = None) -> set[str]:
    """Return all Discovered-section titles from the current checkpoint.md."""
    path = checkpoint_path(session_id, data_root)
    try:
        with open(path) as f:
            text = f.read()
    except (FileNotFoundError, OSError):
        return set()
    return set(extract_titles_from_learning(text))


def _read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def run_validators_for_checkpoint(
    session_id: str,
    project_id: str,
    prior_titles: set[str] | None = None,
    expected_revisions: list[dict] | None = None,
    budgets: dict | None = None,
    data_root: str | None = None,
) -> list[Violation]:
    """Run all validators against the current checkpoint/memory artifacts."""
    if prior_titles is None:
        prior_titles = load_prior_discovered_titles(session_id, data_root)
    if expected_revisions is None:
        expected_revisions = []

    check_content = _read_file(checkpoint_path(session_id, data_root))
    mem_content = _read_file(memory_path(project_id, data_root))

    violations: list[Violation] = []

    if check_content:
        violations.extend(validate_snapshot(check_content, "checkpoint.md"))
        violations.extend(validate_learning(check_content, "checkpoint.md", prior_titles))
    else:
        violations.append(Violation(
            file="checkpoint.md",
            rule="topic-missing",
            severity="error",
            detail="checkpoint file did not exist after writer finished",
        ))

    if mem_content and expected_revisions:
        violations.extend(validate_memory(mem_content, expected_revisions))

    b = budgets or {"checkpoint": 11_000, "memory": 10_000, "progress_per_task": 6_000}

    if check_content:
        violations.extend(validate_budget(check_content, b["checkpoint"], "checkpoint.md"))
    if mem_content:
        violations.extend(validate_budget(mem_content, b["memory"], "MEMORY.md"))

    if check_content:
        violations.extend(validate_budget_sections(check_content, CHECKPOINT_SECTION_BUDGETS, "checkpoint.md"))
    if mem_content:
        violations.extend(validate_budget_sections(mem_content, MEMORY_SECTION_BUDGETS, "MEMORY.md"))

    return violations


def run_task_progress_validators(session_id: str, data_root: str | None = None) -> list[Violation]:
    """Validate every present tasks/<id>/progress.md."""
    violations: list[Violation] = []
    task_root = os.path.join(meta_dir(session_id, data_root), "tasks")
    try:
        task_dirs = os.listdir(task_root)
    except (FileNotFoundError, OSError):
        return violations

    for tid in task_dirs:
        prog_path = os.path.join(task_root, tid, "progress.md")
        prog = _read_file(prog_path)
        if prog:
            violations.extend(validate_progress(prog, f"tasks/{tid}/progress.md"))
    return violations


def quarantine_checkpoint(session_id: str, data_root: str | None = None) -> None:
    """Rename checkpoint.md → checkpoint.invalid.md."""
    dir_path = meta_dir(session_id, data_root)
    src = os.path.join(dir_path, "checkpoint.md")
    dst = os.path.join(dir_path, "checkpoint.invalid.md")
    try:
        os.rename(src, dst)
    except OSError:
        pass


def build_reflection_message(
    errors: list[Violation],
    paths: dict,
) -> str:
    """Build system-reminder body for the writer subagent on validation-failure retry."""
    grouped: dict[str, list[str]] = {}
    for e in errors:
        grouped.setdefault(e.file, []).append(f"- {e.detail}")

    sections = []
    for file, lines in grouped.items():
        sections.append(f"{file}:\n" + "\n".join(lines))

    parts = [
        "<system-reminder>",
        "The previous attempt at this checkpoint had validation errors. Read your output at the absolute paths below, fix ONLY the issues listed, and write again. Other content may stay the same.",
        "",
        "\n\n".join(sections),
        "",
        f"CHECKPOINT_PATH = {paths.get('checkpoint', '')}",
        f"MEMORY_PATH     = {paths.get('memory', '')}",
        "</system-reminder>",
    ]
    return "\n".join(parts)


def build_extraction_reflection(violations: list[Violation]) -> str:
    """Build reflection prompt for extract-required budget violations."""
    over_budget = [v for v in violations if v.severity == "extract-required"]
    files = ", ".join(f"{v.file} ({v.detail})" for v in over_budget)
    return (
        f"EXTRACTION REQUIRED: The following files exceed their token budget: {files}.\n\n"
        "Extract the LESS-IMPORTANT topic cluster from the over-budget file into a new spillover file:\n"
        "  - Checkpoint spillover: checkpoint-<topic>.md (sibling of checkpoint.md)\n"
        "  - Memory spillover: MEMORY-<topic>.md (sibling of MEMORY.md)\n\n"
        "Selection criteria for 'less important' (extract THESE first):\n"
        "  - Already-stable decisions unlikely to be revisited\n"
        "  - Dead ends before Discovered entries\n"
        "  - Historical / completed steps before recent / in-progress\n"
        "  - Topics not directly relevant to the current focus task\n\n"
        "After extraction, edit the main file to:\n"
        "  - REMOVE the extracted lines\n"
        "  - INSERT an index line near the bottom:\n"
        '    "- See <spillover-filename>.md (N entries) — short summary"\n\n'
        "Re-validation will run after this single extraction."
    )
