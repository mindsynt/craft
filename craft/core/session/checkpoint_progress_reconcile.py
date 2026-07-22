"""Checkpoint progress reconciler — ported from checkpoint-progress-reconcile.ts."""

import os
import re

from craft.core.session.checkpoint_paths import checkpoint_path, tasks_dir


def parse_written_at(body: str) -> int | None:
    """Parse written-at field from markdown frontmatter. Returns None when absent."""
    fm = re.match(r"^---\n([\s\S]*?)\n---\n", body)
    if not fm:
        return None
    for line in fm.group(1).split("\n"):
        if line.startswith("written-at:"):
            try:
                return int(line[len("written-at:"):].strip())
            except (ValueError, TypeError):
                return None
    return None


def parse_reconciled_map(main_checkpoint: str) -> dict[str, int]:
    """Parse last-reconciled-written-at markers from checkpoint.md."""
    result: dict[str, int] = {}
    pattern = re.compile(
        r"(?<!`)\(progress:\s*tasks\/([^/]+)\/progress\.md,\s*last-reconciled-written-at:\s*(\d+)\)"
    )
    for m in pattern.finditer(main_checkpoint):
        try:
            value = int(m.group(2))
            result[m.group(1)] = value
        except (ValueError, TypeError):
            continue
    return result


def build_progress_diff_items(session_id: str, data_root: str | None = None) -> list[dict]:
    """Scan tasks/*/progress.md and compare written-at against prior reconciliation."""
    main_path = checkpoint_path(session_id, data_root)
    main_content = ""
    try:
        with open(main_path) as f:
            main_content = f.read()
    except (FileNotFoundError, OSError):
        pass

    reconciled = parse_reconciled_map(main_content)
    root = tasks_dir(session_id, data_root)

    try:
        entries = os.listdir(root)
    except (FileNotFoundError, OSError):
        return []

    items: list[dict] = []
    for entry in entries:
        fp = os.path.join(root, entry, "progress.md")
        try:
            with open(fp) as f:
                body = f.read()
        except (FileNotFoundError, OSError):
            continue

        written_at = parse_written_at(body)
        if written_at is None:
            continue

        prior = reconciled.get(entry)
        if prior is None:
            items.append({"taskId": entry, "writtenAt": written_at, "status": "NEW"})
        elif written_at > prior:
            items.append({"taskId": entry, "writtenAt": written_at, "status": "CHANGED", "prior": prior})
    return items


def render_progress_diff_block(items: list[dict]) -> str:
    """Render markdown injection block for writer prompt."""
    if not items:
        return ""
    lines = ["SUBAGENT PROGRESS to integrate (since last reconcile):"]
    for it in items:
        if it["status"] == "NEW":
            lines.append(f'  - {it["taskId"]} (NEW, written-at={it["writtenAt"]})')
        else:
            lines.append(f'  - {it["taskId"]} (CHANGED, written-at={it["writtenAt"]}, prior={it["prior"]})')
    lines.append("")
    lines.append(
        "For each: Read tasks/<TID>/progress.md, integrate §4 (verbatim commands) verbatim into main §5 Current work; "
        "integrate §5 (outcome+discoveries) into main §5 or §7 as appropriate. Then update the corresponding §4 line "
        "in main checkpoint to:"
    )
    lines.append(
        "  (progress: tasks/<TID>/progress.md, last-reconciled-written-at: <written-at from above>)"
    )
    return "\n".join(lines)


def build_progress_diff(session_id: str, data_root: str | None = None) -> str:
    """High-level convenience: scan + render in one call. Returns empty string when nothing to reconcile."""
    try:
        items = build_progress_diff_items(session_id, data_root)
    except Exception:
        items = []
    return render_progress_diff_block(items)
