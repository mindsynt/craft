"""Import Codex sessions from ~/.codex/sessions/*.jsonl.

移植自 MiMo-Code packages/opencode/src/session/codex-import.ts
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from craft.core.id import ascending as gen_id, descending as gen_desc


def _parse_timestamp(ts: str | None) -> int:
    """Parse a timestamp string into milliseconds."""
    if not ts:
        return int(time.time() * 1000)
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, AttributeError):
        return int(time.time() * 1000)


def _resolve_project(cwd: str) -> dict[str, Any]:
    """Resolve a project from a working directory."""
    if not cwd or not os.path.exists(cwd):
        return {"id": "global", "worktree": cwd or "/", "vcs": None}

    def find_git_dir(path: str) -> str | None:
        current = os.path.abspath(path)
        while True:
            git_path = os.path.join(current, ".git")
            if os.path.exists(git_path):
                return git_path
            parent = os.path.dirname(current)
            if parent == current:
                return None
            current = parent

    git_dir = find_git_dir(cwd)
    if not git_dir:
        return {"id": "global", "worktree": cwd, "vcs": None}

    import hashlib
    return {
        "id": f"prj_{hashlib.md5(cwd.encode()).hexdigest()[:12]}",
        "worktree": cwd,
        "vcs": "git",
    }


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """Parse function call arguments."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
    if isinstance(raw, dict):
        return raw
    return {}


def parse_codex_jsonl(
    text: str,
    session_id: str,
) -> dict[str, Any] | None:
    """Parse Codex JSONL content into Craft session format.

    Returns {
        cwd, version, title, time_created, time_updated, messages
    } or None if no messages.
    """
    entries = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not entries:
        return None

    cwd: str | None = None
    version: str | None = None
    time_created: int | None = None
    time_updated = 0
    title: str | None = None

    messages: list[dict[str, Any]] = []
    tool_by_call_id: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    last_user_id: str | None = None

    def flush_assistant() -> None:
        nonlocal current
        if current is not None:
            messages.append(current)
        current = None

    def ensure_assistant(ts: int) -> dict[str, Any]:
        nonlocal current, last_user_id
        if last_user_id is None:
            uid = gen_id("message")
            messages.append({
                "info": {
                    "id": uid,
                    "sessionID": session_id,
                    "role": "user",
                    "agent": "main",
                    "time": {"created": ts},
                    "model": {"providerID": "openai", "modelID": "unknown"},
                },
                "parts": [],
            })
            last_user_id = uid

        if current is None or current["info"]["role"] != "assistant":
            flush_assistant()
            current = {
                "info": {
                    "id": gen_id("message"),
                    "sessionID": session_id,
                    "role": "assistant",
                    "time": {"created": ts, "completed": ts},
                    "parentID": last_user_id,
                    "modelID": "unknown",
                    "providerID": "openai",
                    "mode": "build",
                    "agent": "main",
                    "path": {"cwd": cwd or "", "root": cwd or ""},
                    "cost": 0,
                    "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
                },
                "parts": [],
            }

        current["info"]["time"]["completed"] = ts
        return current

    for entry in entries:
        entry_type = entry.get("type", "")
        payload = entry.get("payload") or {}
        ts = _parse_timestamp(entry.get("timestamp"))

        if time_created is None:
            time_created = ts
        time_updated = max(time_updated, ts)

        if entry_type == "session_meta" and payload:
            cwd = payload.get("cwd") or cwd
            cli_ver = payload.get("cli_version", "unknown")
            version = f"codex-{cli_ver}"
            meta_ts = _parse_timestamp(payload.get("timestamp"))
            if time_created is None or meta_ts < time_created:
                time_created = meta_ts
            continue

        if entry_type != "response_item" or not payload:
            continue

        item_type = payload.get("type", "")

        if item_type == "message":
            role = payload.get("role", "")
            content = payload.get("content") or []
            if not isinstance(content, list):
                content = []

            if role in ("user", "developer"):
                text_blocks = [
                    c["text"]
                    for c in content
                    if isinstance(c, dict) and c.get("type") in ("input_text", "text")
                    and isinstance(c.get("text"), str) and c["text"].strip()
                ]
                if not text_blocks:
                    continue

                flush_assistant()
                msg_id = gen_id("message")
                parts: list[dict[str, Any]] = [
                    {
                        "part": {
                            "id": gen_id("part"),
                            "sessionID": session_id,
                            "messageID": msg_id,
                            "type": "text",
                            "text": txt,
                        },
                        "time": ts,
                    }
                    for txt in text_blocks
                ]

                messages.append({
                    "info": {
                        "id": msg_id,
                        "sessionID": session_id,
                        "role": "user",
                        "agent": "main",
                        "time": {"created": ts},
                        "model": {"providerID": "openai", "modelID": "unknown"},
                    },
                    "parts": parts,
                })
                last_user_id = msg_id

                if title is None:
                    candidate = next(
                        (x for x in text_blocks if x.strip() and not x.strip().startswith("<")),
                        None,
                    )
                    if candidate:
                        import re
                        title = re.sub(r"\s+", " ", candidate.strip())[:100]
                continue

            if role == "assistant":
                assistant = ensure_assistant(ts)
                for c in content:
                    if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                        text = c.get("text", "")
                        if text.strip():
                            assistant["parts"].append({
                                "part": {
                                    "id": gen_id("part"),
                                    "sessionID": session_id,
                                    "messageID": assistant["info"]["id"],
                                    "type": "text",
                                    "text": text,
                                },
                                "time": ts,
                            })
                continue
            continue

        if item_type == "reasoning":
            assistant = ensure_assistant(ts)
            summary = payload.get("summary") or []
            summary_text = "".join(s.get("text", "") for s in summary if isinstance(s, dict))
            if summary_text.strip():
                assistant["parts"].append({
                    "part": {
                        "id": gen_id("part"),
                        "sessionID": session_id,
                        "messageID": assistant["info"]["id"],
                        "type": "reasoning",
                        "text": summary_text,
                        "time": {"start": ts, "end": ts},
                    },
                    "time": ts,
                })
            continue

        if item_type in ("function_call", "custom_tool_call"):
            assistant = ensure_assistant(ts)
            call_id = payload.get("call_id") or gen_id("part")
            name = payload.get("name") or "unknown"
            if item_type == "function_call":
                input_data = _parse_arguments(payload.get("arguments"))
            else:
                input_data = {"raw": str(payload.get("input", ""))}

            part = {
                "id": gen_id("part"),
                "sessionID": session_id,
                "messageID": assistant["info"]["id"],
                "type": "tool",
                "callID": call_id,
                "tool": name,
                "state": {
                    "status": "pending",
                    "input": input_data,
                    "raw": json.dumps(input_data, ensure_ascii=False),
                },
            }
            assistant["parts"].append({"part": part, "time": ts})
            tool_by_call_id[call_id] = {"part": part, "start": ts}
            continue

        if item_type in ("function_call_output", "custom_tool_call_output"):
            call_id = payload.get("call_id", "")
            ref = tool_by_call_id.get(call_id)
            if ref is None:
                continue
            output = payload.get("output", "")
            if not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False)
            ref["part"]["state"] = {
                "status": "completed",
                "input": ref["part"]["state"].get("input", {}),
                "output": output,
                "title": ref["part"]["tool"],
                "metadata": {},
                "time": {"start": ref["start"], "end": ts},
            }
            continue

    flush_assistant()

    if not messages:
        return None

    return {
        "cwd": cwd or "",
        "version": version or "codex",
        "title": title or "Codex session",
        "time_created": time_created or int(time.time() * 1000),
        "time_updated": time_updated or time_created or int(time.time() * 1000),
        "messages": messages,
    }


async def run_codex_import(
    db: sqlite3.Connection,
    force: bool = False,
) -> dict[str, Any]:
    """Import Codex sessions from ~/.codex/sessions/*.jsonl.

    Returns stats dict with scanned, imported, resynced, skipped, errors.
    """
    root = os.path.join(str(Path.home()), ".codex", "sessions")
    stats: dict[str, Any] = {
        "scanned": 0,
        "imported": 0,
        "resynced": 0,
        "skipped": 0,
        "errors": [],
    }

    if not os.path.exists(root):
        return stats

    # Ensure tables exist
    db.execute("""
        CREATE TABLE IF NOT EXISTS project (
            id TEXT PRIMARY KEY,
            worktree TEXT NOT NULL,
            vcs TEXT,
            sandboxes TEXT DEFAULT '[]',
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS session (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            directory TEXT NOT NULL,
            title TEXT NOT NULL,
            version TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT 'main',
            time_created INTEGER NOT NULL,
            data TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS part (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            data TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS external_import (
            source TEXT NOT NULL,
            source_key TEXT NOT NULL,
            session_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_mtime INTEGER NOT NULL,
            time_imported INTEGER NOT NULL,
            message_ids TEXT,
            PRIMARY KEY (source, source_key)
        )
    """)
    db.commit()

    jsonl_files = sorted(Path(root).glob("**/*.jsonl"))
    now = int(time.time() * 1000)

    for filepath in jsonl_files:
        stats["scanned"] += 1
        try:
            source_key = filepath.stem
            mtime = int(filepath.stat().st_mtime)

            cursor = db.execute(
                "SELECT session_id, source_mtime, message_ids FROM external_import WHERE source = ? AND source_key = ?",
                ("codex", source_key),
            )
            row = cursor.fetchone()

            if row and row[1] == mtime and not force:
                stats["skipped"] += 1
                continue

            existing_session_id = None
            existing_updated = None
            if row:
                existing_session_id = row[0]
                cursor2 = db.execute(
                    "SELECT time_updated FROM session WHERE id = ?",
                    (existing_session_id,),
                )
                sess_row = cursor2.fetchone()
                if sess_row:
                    existing_updated = sess_row[0]
                else:
                    db.execute(
                        "DELETE FROM external_import WHERE source = ? AND source_key = ?",
                        ("codex", source_key),
                    )
                    existing_session_id = None

            session_id = existing_session_id or gen_desc("session")

            text = filepath.read_text(encoding="utf-8")
            parsed = parse_codex_jsonl(text, session_id)
            if parsed is None or not parsed["messages"]:
                stats["skipped"] += 1
                continue

            project = _resolve_project(parsed["cwd"])
            message_ids = [m["info"]["id"] for m in parsed["messages"]]

            db.execute(
                """INSERT OR IGNORE INTO project (id, worktree, vcs, sandboxes, time_created, time_updated)
                   VALUES (?, ?, ?, '[]', ?, ?)""",
                (project["id"], project["worktree"], project["vcs"],
                 parsed["time_created"], parsed["time_updated"]),
            )

            if existing_session_id:
                if row and row[2]:
                    old_ids = json.loads(row[2]) if isinstance(row[2], str) else []
                    for i in range(0, len(old_ids), 500):
                        batch = old_ids[i:i + 500]
                        placeholders = ",".join("?" * len(batch))
                        db.execute(f"DELETE FROM message WHERE id IN ({placeholders})", batch)
                else:
                    db.execute("DELETE FROM message WHERE session_id = ?", (existing_session_id,))

                db.execute(
                    """UPDATE session SET project_id=?, directory=?, version=?, time_updated=?
                       WHERE id=?""",
                    (project["id"], parsed["cwd"], parsed.get("version", "codex"),
                     max(existing_updated or 0, parsed["time_updated"]), existing_session_id),
                )
            else:
                db.execute(
                    """INSERT INTO session (id, project_id, slug, directory, title, version, time_created, time_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, project["id"], source_key[:12], parsed["cwd"],
                     parsed["title"], parsed.get("version", "codex"),
                     parsed["time_created"], parsed["time_updated"]),
                )

            for m in parsed["messages"]:
                info = m["info"].copy()
                info.pop("sessionID", None)
                info.pop("agentID", None)
                db.execute(
                    """INSERT OR REPLACE INTO message (id, session_id, agent_id, time_created, data)
                       VALUES (?, ?, ?, ?, ?)""",
                    (info["id"], session_id, "main", info["time"]["created"],
                     json.dumps(info, ensure_ascii=False)),
                )
                for p in m.get("parts", []):
                    pdata = p["part"].copy()
                    pdata.pop("sessionID", None)
                    pdata.pop("messageID", None)
                    db.execute(
                        """INSERT OR REPLACE INTO part (id, message_id, session_id, time_created, data)
                           VALUES (?, ?, ?, ?, ?)""",
                        (pdata["id"], info["id"], session_id, p["time"],
                         json.dumps(pdata, ensure_ascii=False)),
                    )

            db.execute(
                """INSERT OR REPLACE INTO external_import (source, source_key, session_id, source_path, source_mtime, time_imported, message_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("codex", source_key, session_id, str(filepath), mtime, now, json.dumps(message_ids)),
            )
            db.commit()

            if existing_session_id:
                stats["resynced"] += 1
            else:
                stats["imported"] += 1

        except Exception as e:
            stats["errors"].append(f"{filepath}: {e}")

    return stats
