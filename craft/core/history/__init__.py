"""历史记录 — 包结构

移植自 packages/opencode/src/history/
会话历史 FTS 索引、搜索、归档
"""

from __future__ import annotations

from craft.core.history.extract import (
    KINDS,
    DEFAULT_KINDS,
    Extracted,
    extract,
)
from craft.core.history.fts import (
    FTS_SCHEMA_SQL,
    build_fts_query,
    LRU,
    Resolver,
)
from craft.core.history.writer import (
    HistoryWriter,
)
from craft.core.history.service import (
    HistoryEntry,
    HistoryStore,
    SearchHit,
    MessagePart,
    MessageContext,
    AroundResult,
    SearchInput,
    AroundInput,
    HistoryService,
    HistoryBackfill,
    backfill_all,
)

# 模块全局实例（保留原实例以保持兼容）
history = HistoryStore()
writer = HistoryWriter()
backfill = HistoryBackfill()
service = HistoryService()

__all__ = [
    "KINDS", "DEFAULT_KINDS", "Extracted", "extract",
    "FTS_SCHEMA_SQL", "build_fts_query", "LRU", "Resolver",
    "HistoryWriter",
    "HistoryEntry", "HistoryStore",
    "SearchHit", "MessagePart", "MessageContext", "AroundResult",
    "SearchInput", "AroundInput",
    "HistoryService", "HistoryBackfill", "backfill_all",
    "history", "writer", "backfill", "service",
]
