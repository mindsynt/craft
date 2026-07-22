"""
CLI Session 命令 — 移植自 packages/opencode/src/cli/cmd/session.ts
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)


async def handle_session_list(args: dict) -> None:
    """列出所有会话"""
    try:
        from craft.core.session import list_sessions
        sessions = await list_sessions()
    except ImportError:
        from craft.core.session import SessionStore
        store = SessionStore()
        sessions = store.list()

    limit = int(args.get("limit", 20))
    sessions = sessions[:limit]

    if not sessions:
        print("No sessions found.")
        return

    print(f"{'ID':<24} {'Name':<32} {'Created':<20} {'Messages'}")
    print("-" * 90)
    for s in sessions:
        sid = s.get("id", s.get("session_id", "?"))
        name = s.get("name", s.get("title", ""))[:30]
        created = s.get("created_at", "")
        if isinstance(created, (int, float)):
            created = time.strftime("%Y-%m-%d %H:%M", time.localtime(created))
        msg_count = s.get("message_count", s.get("messages", 0))
        print(f"{sid[:22]:<24} {name:<32} {created:<20} {msg_count}")


async def handle_session_show(args: dict) -> None:
    """显示会话详情"""
    session_id = args.get("session_id", "")
    if not session_id:
        print("Error: session_id is required")
        return
    print(f"Session: {session_id} (details not yet implemented)")


async def handle_session_delete(args: dict) -> None:
    """删除会话"""
    session_id = args.get("session_id", "")
    if not session_id:
        print("Error: session_id is required")
        return
    print(f"Deleting session: {session_id} (not yet implemented)")
