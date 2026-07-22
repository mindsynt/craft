"""Import Claude Code sessions from ~/.claude/projects/*/*.jsonl.

移植自 MiMo-Code packages/opencode/src/session/claude-import.ts
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from craft.core.id import ascending as gen_id, descending as gen_desc


def encode_dir(cwd: str) -> str:
    """Encode a directory path for folder-name usage (diagnostics only)."""
    return re.sub(r"[^a-zA-Z0-9]", "-", cwd)


def _split_model(model: str | None) -> tuple[str, str]:
    """Split a model string like 'anthropic/claude-3-opus' into (provider_id, model_id)."""
    if not model:
        return ("anthropic", "unknown")
    idx = model.find("/")
    if idx == -1:
        return ("anthropic", model)
    return (model[:idx], model[idx + 1:])


def _tokens_from(usage: dict[str, Any] | None) -> dict[str, Any]:
    """Extract token usage from a Claude Code message usage object."""
    u = usage or {}
    return {
        "input": u.get("input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "reasoning": 0,
        "cache": {
            "read": u.get("cache_read_input_tokens", 0),
            "write": u.get("cache_creation_input_tokens", 0),
        },
    }


def _stringify_tool_content(content: Any) -> str:
    """Stringify tool result content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            else:
                parts.append(json.dumps(b, ensure_ascii=False))
        return "\n".join(parts)
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def parse_claude_jsonl(
    text: str,
    session_id: str,
) -> dict[str, Any] | None:
    """Parse Claude Code JSONL content into Craft session format.

    Returns {
        cwd, version, title, time_created, time_updated, messages
    } or None if parsing yields no messages.
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
    tool_by_call: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    last_user_id: str | None = None
    last_model = ("anthropic", "unknown")

    def flush_assistant() -> None:
        nonlocal current
        if current is not None:
            messages.append(current)
        current = None

    for entry in entries:
        entry_type = entry.get("type")
        if entry_type not in ("user", "assistant"):
            continue
        ts_str = entry.get("timestamp")
        t = int(time.time() * 1000)
        if ts_str:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                t = int(dt.timestamp() * 1000)
            except (ValueError, AttributeError):
                pass

        if cwd is None and entry.get("cwd"):
            cwd = entry["cwd"]
        if version is None and entry.get("version"):
            version = entry["version"]
        if time_created is None:
            time_created = t
        time_updated = max(time_updated, t)

        msg = entry.get("message")
        if not msg:
            continue

        if entry_type == "user":
            content = msg.get("content")
            blocks: list[dict] = []
            if isinstance(content, list):
                blocks = content

            # Handle tool results
            for r in blocks:
                if isinstance(r, dict) and r.get("type") == "tool_result":
                    ref = tool_by_call.get(r.get("tool_use_id", ""))
                    if ref is None:
                        continue
                    out_text = _stringify_tool_content(r.get("content"))
                    is_error = r.get("is_error", False)
                    if is_error:
                        ref["part"]["state"] = {
                            "status": "error",
                            "input": ref["part"]["state"].get("input", {}),
                            "error": out_text,
                            "time": {"start": ref["start"], "end": t},
                        }
                    else:
                        ref["part"]["state"] = {
                            "status": "completed",
                            "input": ref["part"]["state"].get("input", {}),
                            "output": out_text,
                            "title": ref["part"]["tool"],
                            "metadata": {},
                            "time": {"start": ref["start"], "end": t},
                        }

            text_blocks: list[str] = []
            if isinstance(content, str):
                content_s = content.strip()
                if content_s:
                    text_blocks = [content]
            else:
                text_blocks = [
                    b["text"]
                    for b in blocks
                    if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str) and b["text"].strip()
                ]
            image_blocks = [
                b for b in blocks
                if isinstance(b, dict) and b.get("type") == "image" and b.get("source")
            ]

            if not text_blocks and not image_blocks:
                continue

            flush_assistant()
            msg_id = gen_id("message")
            parts: list[dict[str, Any]] = []

            for txt in text_blocks:
                parts.append({
                    "part": {
                        "id": gen_id("part"),
                        "sessionID": session_id,
                        "messageID": msg_id,
                        "type": "text",
                        "text": txt,
                    },
                    "time": t,
                })

            for b in image_blocks:
                source = b.get("source", {})
                mime = source.get("media_type", "image/png")
                if source.get("type") == "base64":
                    url = f"data:{mime};base64,{source.get('data', '')}"
                else:
                    url = source.get("url", "")
                if url:
                    parts.append({
                        "part": {
                            "id": gen_id("part"),
                            "sessionID": session_id,
                            "messageID": msg_id,
                            "type": "file",
                            "mime": mime,
                            "url": url,
                        },
                        "time": t,
                    })

            model_info = {
                "providerID": last_model[0],
                "modelID": last_model[1],
            }
            messages.append({
                "info": {
                    "id": msg_id,
                    "sessionID": session_id,
                    "role": "user",
                    "agent": "main",
                    "time": {"created": t},
                    "model": model_info,
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
                    title = re.sub(r"\s+", " ", candidate.strip())[:100]
            continue

        # assistant
        model_str = msg.get("model")
        if model_str:
            last_model = _split_model(model_str)
        model = last_model

        if last_user_id is None:
            uid = gen_id("message")
            messages.append({
                "info": {
                    "id": uid,
                    "sessionID": session_id,
                    "role": "user",
                    "agent": "main",
                    "time": {"created": t},
                    "model": {"providerID": model[0], "modelID": model[1]},
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
                    "time": {"created": t, "completed": t},
                    "parentID": last_user_id,
                    "modelID": model[1],
                    "providerID": model[0],
                    "mode": "build",
                    "agent": "main",
                    "path": {"cwd": cwd or "", "root": cwd or ""},
                    "cost": 0,
                    "tokens": _tokens_from(msg.get("usage")),
                },
                "parts": [],
            }

        a_info = current["info"]
        a_info["time"]["completed"] = t
        a_info["tokens"] = _tokens_from(msg.get("usage"))
        mid = current["info"]["id"]

        msg_content = msg.get("content", [])
        if not isinstance(msg_content, list):
            msg_content = []

        for b in msg_content:
            if not isinstance(b, dict):
                continue
            btype = b.get("type")
            if btype in ("thinking", "reasoning"):
                text = b.get("thinking", b.get("text", ""))
                current["parts"].append({
                    "part": {
                        "id": gen_id("part"),
                        "sessionID": session_id,
                        "messageID": mid,
                        "type": "reasoning",
                        "text": text,
                        "time": {"start": t, "end": t},
                    },
                    "time": t,
                })
            elif btype == "text":
                text = b.get("text", "")
                current["parts"].append({
                    "part": {
                        "id": gen_id("part"),
                        "sessionID": session_id,
                        "messageID": mid,
                        "type": "text",
                        "text": text,
                    },
                    "time": t,
                })
            elif btype == "tool_use":
                part = {
                    "id": gen_id("part"),
                    "sessionID": session_id,
                    "messageID": mid,
                    "type": "tool",
                    "callID": b.get("id", ""),
                    "tool": b.get("name", ""),
                    "state": {
                        "status": "pending",
                        "input": b.get("input", {}),
                        "raw": json.dumps(b.get("input", {}), ensure_ascii=False),
                    },
                }
                current["parts"].append({
                    "part": part,
                    "time": t,
                })
                tool_by_call[b.get("id", "")] = {"part": part, "start": t}

    flush_assistant()

    if not messages:
        return None

    return {
        "cwd": cwd or "",
        "version": version,
        "title": title or "Claude Code session",
        "time_created": time_created or int(time.time() * 1000),
        "time_updated": time_updated or time_created or int(time.time() * 1000),
        "messages": messages,
    }


def resolve_project(cwd: str) -> dict[str, Any]:
    """Resolve a project from a working directory."""
    if not cwd or not os.path.exists(cwd):
        return {"id": "global", "worktree": cwd or "/", "vcs": None}
    git_dir = _find_git_dir(cwd)
    if not git_dir:
        return {"id": "global", "worktree": cwd, "vcs": None}
    return {"id": _resolve_project_id(cwd), "worktree": cwd, "vcs": "git"}


def _find_git_dir(path: str) -> str | None:
    """Find the .git directory for a given path."""
    current = os.path.abspath(path)
    while True:
        git_path = os.path.join(current, ".git")
        if os.path.exists(git_path):
            return git_path
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _resolve_project_id(path: str) -> str:
    """Resolve a project ID from a path."""
    import hashlib
    return f"prj_{hashlib.md5(path.encode()).hexdigest()[:12]}"


async def run_claude_import(
    db: sqlite3.Connection,
    force: bool = False,
) -> dict[str, Any]:
    """Import Claude Code sessions from ~/.claude/projects/*/*.jsonl.

    Returns stats dict with scanned, imported, resynced, skipped, errors.
    """
    root = os.path.join(str(Path.home()), ".claude", "projects")
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

    # Scan for JSONL files
    jsonl_files = sorted(Path(root).glob("*/*.jsonl"))
    now = int(time.time() * 1000)

    for filepath in jsonl_files:
        stats["scanned"] += 1
        try:
            source_uuid = filepath.stem
            mtime = int(filepath.stat().st_mtime)

            # Check existing import
            cursor = db.execute(
                "SELECT session_id, source_mtime, message_ids FROM external_import WHERE source = ? AND source_key = ?",
                ("cc", source_uuid),
            )
            row = cursor.fetchone()

            if row and row[1] == mtime and not force:
                stats["skipped"] += 1
                continue

            existing_session_id = None
            existing_updated = None
            if row:
                existing_session_id = row[0]
                # Check if session still exists
                cursor2 = db.execute(
                    "SELECT time_updated FROM session WHERE id = ?",
                    (existing_session_id,),
                )
                sess_row = cursor2.fetchone()
                if sess_row:
                    existing_updated = sess_row[0]
                else:
                    # Session was deleted, remove import record
                    db.execute(
                        "DELETE FROM external_import WHERE source = ? AND source_key = ?",
                        ("cc", source_uuid),
                    )
                    existing_session_id = None

            session_id = existing_session_id or gen_desc("session")

            text = filepath.read_text(encoding="utf-8")
            parsed = parse_claude_jsonl(text, session_id)
            if parsed is None or not parsed["messages"]:
                stats["skipped"] += 1
                continue

            project = resolve_project(parsed["cwd"])
            message_ids = [m["info"]["id"] for m in parsed["messages"]]

            # Transaction
            db.execute(
                """INSERT OR IGNORE INTO project (id, worktree, vcs, sandboxes, time_created, time_updated)
                   VALUES (?, ?, ?, '[]', ?, ?)""",
                (project["id"], project["worktree"], project["vcs"],
                 parsed["time_created"], parsed["time_updated"]),
            )

            if existing_session_id:
                # Remove old messages
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
                    (project["id"], parsed["cwd"], parsed.get("version", "claude-code"),
                     max(existing_updated or 0, parsed["time_updated"]), existing_session_id),
                )
            else:
                db.execute(
                    """INSERT INTO session (id, project_id, slug, directory, title, version, time_created, time_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, project["id"], source_uuid[:12], parsed["cwd"],
                     parsed["title"], parsed.get("version", "claude-code"),
                     parsed["time_created"], parsed["time_updated"]),
                )

            for m in parsed["messages"]:
                info = m["info"].copy()
                info.pop("sessionID", None)
                info.pop("agentID", None)
                db.execute(
                    """INSERT OR REPLACE INTO message (id, session_id, agent_id, time_created, data)
                       VALUES (?, ?, ?, ?, ?)""",
                    (info["id"], session_id, "main", info["time"]["created"], json.dumps(info, ensure_ascii=False)),
                )
                for p in m.get("parts", []):
                    pdata = p["part"].copy()
                    pdata.pop("sessionID", None)
                    pdata.pop("messageID", None)
                    db.execute(
                        """INSERT OR REPLACE INTO part (id, message_id, session_id, time_created, data)
                           VALUES (?, ?, ?, ?, ?)""",
                        (pdata["id"], info["id"], session_id, p["time"], json.dumps(pdata, ensure_ascii=False)),
                    )

            db.execute(
                """INSERT OR REPLACE INTO external_import (source, source_key, session_id, source_path, source_mtime, time_imported, message_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("cc", source_uuid, session_id, str(filepath), mtime, now, json.dumps(message_ids)),
            )
            db.commit()

            if existing_session_id:
                stats["resynced"] += 1
            else:
                stats["imported"] += 1

        except Exception as e:
            stats["errors"].append(f"{filepath}: {e}")

    return stats
