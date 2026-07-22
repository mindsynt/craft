"""External import SQL schema — tracks imported sessions from external sources.

移植自 MiMo-Code packages/opencode/src/session/external-import.sql.ts
"""

from __future__ import annotations

from typing import Literal

# External source identifier
ExternalSource = Literal["cc", "codex", "opencode"]

# Table creation SQL for external_import
EXTERNAL_IMPORT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS external_import (
    source TEXT NOT NULL,
    source_key TEXT NOT NULL,
    session_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_mtime INTEGER NOT NULL,
    time_imported INTEGER NOT NULL,
    message_ids TEXT,
    PRIMARY KEY (source, source_key)
);
"""
