"""External import orchestrator — scan, import, and re-sync sessions from external tools.

移植自 MiMo-Code packages/opencode/src/session/external-import.ts
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from craft.core.session.claude_import import run_claude_import
from craft.core.session.codex_import import run_codex_import

ALL_SOURCES = ["cc", "codex", "opencode"]


async def scan_external_sources() -> dict[str, dict[str, Any]]:
    """Pre-scan: per-source availability + total/already-imported session counts.

    Returns:
        {
            "cc": {"available": bool, "sessions": int, "imported": int},
            "codex": {"available": bool, "sessions": int, "imported": int},
            "opencode": {"available": bool, "sessions": int, "imported": int},
        }
    """
    from craft.core.storage import db as default_db

    def imported_by_source(source: str) -> int:
        try:
            cursor = default_db.execute(
                "SELECT COUNT(*) AS n FROM external_import WHERE source = ?",
                (source,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    result: dict[str, dict[str, Any]] = {
        "cc": {"available": False, "sessions": 0, "imported": 0},
        "codex": {"available": False, "sessions": 0, "imported": 0},
        "opencode": {"available": False, "sessions": 0, "imported": 0},
    }

    # CC (Claude Code)
    cc_root = os.path.join(str(Path.home()), ".claude", "projects")
    if os.path.exists(cc_root):
        try:
            files = list(Path(cc_root).glob("*/*.jsonl"))
            result["cc"] = {
                "available": True,
                "sessions": len(files),
                "imported": imported_by_source("cc"),
            }
        except Exception as e:
            pass

    # Codex
    codex_root = os.path.join(str(Path.home()), ".codex", "sessions")
    if os.path.exists(codex_root):
        try:
            files = list(Path(codex_root).glob("**/*.jsonl"))
            result["codex"] = {
                "available": True,
                "sessions": len(files),
                "imported": imported_by_source("codex"),
            }
        except Exception as e:
            pass

    # OpenCode / Craft (own DB)
    default_db_path = os.path.join(str(Path.home()), ".craft", "craft.db")
    if os.path.exists(default_db_path):
        try:
            conn = sqlite3.connect(f"file:{default_db_path}?mode=ro", uri=True)
            try:
                cursor = conn.execute("SELECT count(*) AS n FROM session")
                row = cursor.fetchone()
                n = row[0] if row else 0
                result["opencode"] = {
                    "available": True,
                    "sessions": n,
                    "imported": imported_by_source("opencode"),
                }
            finally:
                conn.close()
        except Exception:
            pass

    return result


async def run_all_imports(
    db: sqlite3.Connection,
    sources: list[str] | None = None,
    force: bool = False,
) -> dict[str, dict[str, Any]]:
    """Run all external imports.

    Args:
        db: SQLite database connection
        sources: List of sources to import ("cc", "codex", "opencode"). Default: all.
        force: Force re-import even if mtime unchanged.

    Returns:
        {source: {scanned, imported, resynced, skipped, errors}}
    """
    if sources is None:
        sources = list(ALL_SOURCES)
    source_set = set(sources)

    result: dict[str, dict[str, Any]] = {
        "cc": {"scanned": 0, "imported": 0, "resynced": 0, "skipped": 0, "errors": []},
        "codex": {"scanned": 0, "imported": 0, "resynced": 0, "skipped": 0, "errors": []},
        "opencode": {"scanned": 0, "imported": 0, "resynced": 0, "skipped": 0, "errors": []},
    }

    for source in ALL_SOURCES:
        if source not in source_set:
            continue
        try:
            if source == "cc":
                result["cc"] = await run_claude_import(db, force=force)
            elif source == "codex":
                result["codex"] = await run_codex_import(db, force=force)
            else:
                pass  # opencode import not implemented yet
        except Exception as e:
            result[source]["errors"].append(str(e))

    return result
