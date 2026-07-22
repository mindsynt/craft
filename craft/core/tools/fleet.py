"""Fleet observability — 移植自 packages/opencode/src/tool/fleet.ts

Assemble a structured view of an Orchestrator's children: each session
correlated to its derived liveness, turn telemetry, and optional git
worktree mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Liveness type - matches actor Liveness
Liveness = str  # "progressing" | "stalled" | "success" | "failure" | "cancelled" | "idle"

# Fleet bucket display grouping
FleetBucket = str  # "progressing" | "stalled" | "idle" | "failed" | "cancelled"

BUCKET_ORDER: list[FleetBucket] = ["progressing", "stalled", "idle", "failed", "cancelled"]

HEADINGS: dict[FleetBucket, str] = {
    "progressing": "In progress — progressing (advancing)",
    "stalled": "In progress — stalled (no recent turn)",
    "idle": "Finished / idle",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


@dataclass
class FleetSession:
    """A single child session as the caller sees it before correlation."""
    id: str
    title: str
    directory: str


@dataclass
class WorktreeEntry:
    """One parsed 'git worktree list --porcelain' entry."""
    directory: str
    branch: str | None = None
    ahead: int | None = None


@dataclass
class FleetRow:
    """One fully-correlated row: session identity + liveness + turn telemetry."""
    session_id: str
    title: str
    mode: str
    bucket: FleetBucket
    liveness: Liveness
    status: str
    turn_count: int
    last_activity_ms: int | None = None
    worktree_dir: str | None = None
    branch: str | None = None
    ahead: int | None = None


@dataclass
class FleetSummary:
    """Aggregated fleet view."""
    total: int
    counts: dict[FleetBucket, int] = field(default_factory=lambda: {b: 0 for b in BUCKET_ORDER})
    rows: list[FleetRow] = field(default_factory=list)


@dataclass
class FleetActorInput:
    """An actor row keyed to its session."""
    session: FleetSession
    actor: dict | None  # ActorInfo dict or None


def _bucket_for(liveness: str) -> FleetBucket:
    """Map liveness string to display bucket."""
    mapping: dict[str, FleetBucket] = {
        "progressing": "progressing",
        "stalled": "stalled",
        "failure": "failed",
        "cancelled": "cancelled",
    }
    return mapping.get(liveness, "idle")


def _derive_liveness(
    actor: dict,
    now: float,
    stall_ms: float = 90_000,
) -> str:
    """Derive liveness from an actor info dict.

    Mirrors actor/schema.py derive_liveness but operates on a plain dict
    for callers that don't have the ActorInfo dataclass.
    """
    status = actor.get("status", "idle")
    outcome = actor.get("last_outcome")
    turn_count = actor.get("turn_count", 0)
    last_turn_time = actor.get("last_turn_time", 0)

    if status in ("running", "pending"):
        if turn_count == 0:
            return "progressing"
        return "progressing" if (now - last_turn_time <= stall_ms) else "stalled"

    if outcome == "success":
        return "success"
    if outcome == "failure":
        return "failure"
    if outcome == "cancelled":
        return "cancelled"
    return "idle"


def assemble_fleet(
    inputs: list[FleetActorInput],
    worktrees: list[WorktreeEntry],
    now: float,
    stall_ms: float | None = None,
) -> FleetSummary:
    """Assemble the structured fleet summary from already-fetched inputs.

    Pure function: caller supplies sessions+actors, worktree entries, and clock.
    """
    if stall_ms is None:
        stall_ms = 90_000

    by_dir: dict[str, WorktreeEntry] = {}
    for wt in worktrees:
        by_dir[wt.directory] = wt

    rows: list[FleetRow] = []
    for inp in inputs:
        if inp.actor:
            liveness_str = _derive_liveness(inp.actor, now, stall_ms)
        else:
            liveness_str = "idle"

        bucket = _bucket_for(liveness_str)
        wt = by_dir.get(inp.session.directory)

        row = FleetRow(
            session_id=inp.session.id,
            title=inp.session.title,
            mode=inp.actor.get("agent", "?") if inp.actor else "?",
            bucket=bucket,
            liveness=liveness_str,
            status=inp.actor.get("status", "unknown") if inp.actor else "unknown",
            turn_count=inp.actor.get("turn_count", 0) if inp.actor else 0,
            last_activity_ms=max(0, now - inp.actor["last_turn_time"]) if inp.actor and inp.actor.get("last_turn_time") else None,
            worktree_dir=wt.directory if wt else None,
            branch=wt.branch if wt else None,
            ahead=wt.ahead if wt else None,
        )
        rows.append(row)

    # Sort by bucket order
    bucket_rank = {b: i for i, b in enumerate(BUCKET_ORDER)}
    sorted_rows = sorted(rows, key=lambda r: bucket_rank.get(r.bucket, 99))

    counts: dict[FleetBucket, int] = {b: 0 for b in BUCKET_ORDER}
    for r in sorted_rows:
        if r.bucket in counts:
            counts[r.bucket] += 1

    return FleetSummary(total=len(sorted_rows), counts=counts, rows=sorted_rows)


def _age_of(ms: int | None) -> str:
    """Compact human-readable age."""
    if ms is None:
        return "-"
    if ms < 60_000:
        return f"{ms // 1000}s"
    if ms < 3_600_000:
        return f"{ms // 60_000}m"
    return f"{ms // 3_600_000}h"


def _worktree_cell(row: FleetRow) -> str:
    """Short worktree cell: 'branch (+N) @ dir' for isolated children."""
    if not row.worktree_dir:
        return "shared"
    branch = row.branch or "detached"
    ahead = f" (+{row.ahead})" if row.ahead is not None else ""
    return f"{branch}{ahead} @ {row.worktree_dir}"


def render_fleet_table(summary: FleetSummary) -> str:
    """Render the fleet summary as a grouped, column-aligned text table."""
    if summary.total == 0:
        return "No child sessions."

    c = summary.counts
    running = c.get("progressing", 0) + c.get("stalled", 0)
    parts = [
        f"Fleet: {summary.total} total — {running} running "
        f"({c.get('progressing', 0)} progressing, {c.get('stalled', 0)} stalled), "
        f"{c.get('idle', 0)} idle"
    ]
    if c.get("failed", 0) > 0:
        parts[-1] += f", {c['failed']} failed"
    if c.get("cancelled", 0) > 0:
        parts[-1] += f", {c['cancelled']} cancelled"
    summary_line = parts[-1]

    cols = ["SESSION", "LIVENESS", "AGE", "TURNS", "MODE", "WORKTREE", "TITLE"]
    all_rows = []
    for r in summary.rows:
        all_rows.append([
            r.session_id,
            r.liveness,
            _age_of(r.last_activity_ms),
            str(r.turn_count),
            r.mode,
            _worktree_cell(r),
            r.title,
        ])

    # Column widths sized across ALL rows
    widths = [len(h) for h in cols]
    for i in range(len(cols)):
        for row in all_rows:
            widths[i] = max(widths[i], len(row[i]))

    def _pad(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    blocks: list[str] = []
    for bucket in BUCKET_ORDER:
        count = c.get(bucket, 0)
        if count == 0:
            continue
        body_rows = [
            all_rows[i]
            for i, r in enumerate(summary.rows)
            if r.bucket == bucket
        ]
        block = f"{HEADINGS[bucket]} ({count}):\n" + "\n".join(
            "  " + _pad(row) for row in body_rows
        )
        blocks.append(block)

    return "\n".join([summary_line, "", "  " + _pad(cols), *blocks])
