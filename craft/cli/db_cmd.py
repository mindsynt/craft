"""
CLI DB 命令 — 移植自 packages/opencode/src/cli/cmd/db.ts
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


async def handle_db_query(args: dict) -> None:
    """执行 SQL 查询或打开交互式 shell"""
    query = args.get("query", "")
    db_path = args.get("db_path", "")

    if not db_path:
        from craft.config import CONFIG_DIR
        db_path = str(CONFIG_DIR / "craft.db")

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return

    if query:
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            if rows:
                keys = rows[0].keys()
                format_type = args.get("format", "tsv")
                if format_type == "json":
                    import json
                    print(json.dumps([dict(r) for r in rows], indent=2, default=str))
                else:
                    print("\t".join(keys))
                    for row in rows:
                        print("\t".join(str(row[k] or "") for k in keys))
            else:
                print("Query returned no results")
            conn.close()
        except Exception as e:
            print(f"Query failed: {e}")
    else:
        # Interactive sqlite3 shell
        try:
            import subprocess
            subprocess.run(["sqlite3", db_path])
        except FileNotFoundError:
            print("sqlite3 not found. Install it or provide a query directly.")


async def handle_db_path(args: dict) -> None:
    """打印数据库路径"""
    from craft.config import CONFIG_DIR
    db_path = str(CONFIG_DIR / "craft.db")
    print(db_path)
