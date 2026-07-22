"""
持久化记忆系统 — SQLite FTS5
移植自 MiMo-Code packages/opencode/src/memory/

维护现有 MemoryStore API 的同时补充：
- build_fts_query(): FTS5 查询构建
- 路径解析 (parse_path, parse_cc_path, build_path, resolve_project_id)
- 磁盘扫描与索引 (walk_memory_dir, index_from_disk, reconcile_memory)
- MemoryService: 带 scope/type 过滤和 score floor 的高级搜索
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR


# ═══════════════════════════════════════════════════════════
# 类型定义
# ═══════════════════════════════════════════════════════════

Scope = str  # "global" | "projects" | "sessions" | "cc"
MemoryType = str  # "free" | "memory" | "checkpoint" | "progress" | "notes" | "feedback" | "project" | "reference" | "user"

CC_TYPES: tuple[str, ...] = ("feedback", "project", "reference", "user")


@dataclass
class MemoryLocator:
    scope: str
    scope_id: str
    type: str
    key: str


# ═══════════════════════════════════════════════════════════
# FTS Query Builder (port of fts-query.ts)
# ═══════════════════════════════════════════════════════════

def build_fts_query(raw: str) -> str | None:
    """Build an FTS5 MATCH expression from a free-form user query.

    Tokenizes via Unicode regex for letters, numbers, and underscore.
    Wraps each token as a phrase quote and OR-joins for high recall.

    Returns None when no usable tokens are extracted.
    """
    tokens = re.findall(r"[\w]+", raw, re.UNICODE)
    tokens = [t.strip() for t in tokens if t.strip()]
    if not tokens:
        return None
    quoted = ['"' + t.replace('"', '') + '"' for t in tokens]
    return " OR ".join(quoted)


# ═══════════════════════════════════════════════════════════
# 路径解析 (port of paths.ts)
# ═══════════════════════════════════════════════════════════

# Type patterns for memory/docs classification
TYPE_PATTERNS: list[tuple[re.Pattern, MemoryType]] = [
    (re.compile(r"^memory$", re.IGNORECASE), "memory"),
    (re.compile(r"^memory-", re.IGNORECASE), "memory"),
    (re.compile(r"^checkpoint$"), "checkpoint"),
    (re.compile(r"^checkpoint-"), "checkpoint"),
    (re.compile(r"^tasks/[^/]+/progress$"), "progress"),
    (re.compile(r"^tasks/[^/]+/notes$"), "notes"),
]


def _detect_type(key: str) -> MemoryType:
    """Detect memory type from the file key (stem)."""
    for pattern, mtype in TYPE_PATTERNS:
        if pattern.search(key):
            return mtype
    return "free"


# Matches: <anything>/memory/<scope>[/<scope_id>]/<key>.md
MEMORY_PATH_RE = re.compile(r"/memory/(global|projects|sessions)(?:/([^/]+))?/(.+)\.md$")

# Matches: <anything>/.claude/projects/<slug>/memory/<key>.md
CC_PATH_RE = re.compile(r"/\.claude/projects/([^/]+)/memory/(.+)\.md$")

# Frontmatter: YAML block between leading ---\n and closing \n---\n
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Match indented `type: <word>` inside YAML (the metadata subtree)
METADATA_TYPE_RE = re.compile(r"^[ \t]+type:[ \t]*(\w+)[ \t]*$", re.MULTILINE)


def parse_path(abs_path: str) -> MemoryLocator | None:
    """Parse a MiMo-Code memory file path into a MemoryLocator."""
    m = MEMORY_PATH_RE.search(abs_path)
    if not m:
        return None
    scope = m.group(1)
    scope_id = m.group(2) if m.group(2) else ""
    key_raw = m.group(3)
    return MemoryLocator(
        scope=scope,
        scope_id="" if scope == "global" else scope_id,
        type=_detect_type(key_raw),
        key=key_raw,
    )


def parse_cc_path(abs_path: str) -> MemoryLocator | None:
    """Parse a Claude Code memory file path into a MemoryLocator."""
    m = CC_PATH_RE.search(abs_path)
    if not m:
        return None
    return MemoryLocator(
        scope="cc",
        scope_id=m.group(1),
        type="free",  # type is finalized from frontmatter at index time
        key=m.group(2),
    )


def parse_cc_frontmatter_type(body: str) -> str | None:
    """Extract the metadata.type from a CC frontmatter block."""
    fm = FRONTMATTER_RE.search(body)
    if not fm:
        return None
    inner = fm.group(1)
    t = METADATA_TYPE_RE.search(inner)
    if not t:
        return None
    value = t.group(1)
    return value if value in CC_TYPES else None


def _assert_safe_component(value: str):
    """Reject path traversal or absolute-path injection."""
    for segment in value.split("/"):
        if segment == "..":
            raise ValueError(f"Invalid path component: {value}")
    if value.startswith("/"):
        raise ValueError(f"Invalid path component: {value}")


def build_path(root: str, scope: str, key: str, scope_id: str | None = None) -> str:
    """Build an absolute memory file path from components."""
    if scope_id is not None:
        _assert_safe_component(scope_id)
    _assert_safe_component(key)
    parts = [root, scope]
    if scope != "global" and scope_id:
        parts.append(scope_id)
    parts.append(f"{key}.md")
    return str(Path(*parts))


def resolve_project_id(abs_repo_path: str) -> str:
    """Generate a short project ID from a repo path."""
    return hashlib.sha256(abs_repo_path.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════
# 磁盘扫描与索引 (port of reconcile.ts)
# ═══════════════════════════════════════════════════════════

async def walk_memory_dir(root: str) -> list[str]:
    """Walk a directory tree and collect all .md files."""
    out: list[str] = []
    root_path = Path(root)

    async def _recurse(dir_path: Path):
        try:
            for entry in dir_path.iterdir():
                if entry.is_dir():
                    await _recurse(entry)
                elif entry.is_file() and entry.name.endswith(".md"):
                    out.append(str(entry))
        except FileNotFoundError:
            pass

    await _recurse(root_path)
    return out


async def walk_cc_root(base: str) -> list[str]:
    """Walk <base>/<slug>/memory/**/*.md across every slug under base.

    ENOENT on base returns []; missing memory subdirs are silently skipped.
    """
    out: list[str] = []
    base_path = Path(base)
    try:
        for entry in base_path.iterdir():
            if not entry.is_dir():
                continue
            memory_dir = entry / "memory"
            if memory_dir.exists():
                files = await walk_memory_dir(str(memory_dir))
                out.extend(files)
    except FileNotFoundError:
        pass
    return out


async def index_from_disk(
    abs_path: str,
    loc: MemoryLocator,
    body_type: str,
    db: sqlite3.Connection,
    old_fingerprint: str | None = None,
) -> str:  # "hit" | "updated" | "skipped"
    """Read a memory file from disk and upsert it into the FTS index.

    Returns "hit" if fingerprint matches (no change), "updated" if changed, "skipped" if file not found.
    """
    path_obj = Path(abs_path)
    try:
        stat = path_obj.stat()
    except FileNotFoundError:
        return "skipped"

    fingerprint = f"{stat.st_size}-{stat.st_mtime_ns // 1_000_000}"

    if old_fingerprint and old_fingerprint == fingerprint:
        return "hit"

    body = path_obj.read_text(encoding="utf-8")

    # For CC files, derive type from frontmatter; mimo files keep loc.type from path
    final_type = loc.type
    if body_type == "cc":
        fm_type = parse_cc_frontmatter_type(body)
        if fm_type:
            final_type = fm_type

    now = time.time()
    db.execute(
        """INSERT INTO memory_entries (id, path, scope, scope_id, type, content, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
               scope=excluded.scope, scope_id=excluded.scope_id,
               type=excluded.type, content=excluded.content,
               metadata=excluded.metadata, updated_at=excluded.updated_at""",
        (uuid.uuid4().hex[:16], abs_path, loc.scope, loc.scope_id, final_type, body, "{}", now, now),
    )
    db.commit()
    return "updated"


async def reconcile_memory(root: str, cc_base: str | None = None, db_path: str | None = None) -> dict[str, int]:
    """Reconcile disk files with the FTS index.

    Returns {"indexed": int, "pruned": int}.
    Indexes new/changed files; removes FTS rows for deleted files.
    """
    if db_path is None:
        db_path = str(CONFIG_DIR / "memory.db")

    conn = sqlite3.connect(db_path)

    # Collect disk paths from ALL roots before pruning
    mimo_files = set(await walk_memory_dir(root))
    cc_files = set(await walk_cc_root(cc_base)) if cc_base else set()
    disk_paths = mimo_files | cc_files

    # Get currently indexed paths
    indexed: dict[str, str] = {}
    try:
        cursor = conn.execute("SELECT path, COALESCE(fingerprint, '') FROM memory_fts_idx_view")
        # Fallback: query from memory_entries
        cursor = conn.execute("SELECT path, '' FROM memory_entries")
        for row in cursor:
            indexed[row[0]] = row[1]
    except sqlite3.OperationalError:
        cursor = conn.execute("SELECT path, '' FROM memory_entries")
        for row in cursor:
            indexed[row[0]] = row[1]

    # Actually let's use a simpler approach - store fingerprint in metadata
    cursor = conn.execute("SELECT path, metadata FROM memory_entries")
    for row in cursor:
        import json
        try:
            meta = json.loads(row[1])
            indexed[row[0]] = meta.get("fingerprint", "")
        except (json.JSONDecodeError, AttributeError):
            indexed[row[0]] = ""

    # Direction B: prune dead FTS rows (any path not in either walk)
    pruned = 0
    for p in list(indexed.keys()):
        if p not in disk_paths:
            conn.execute("DELETE FROM memory_entries WHERE path = ?", (p,))
            pruned += 1

    # Direction A: index disk files
    indexed_count = 0
    for p in mimo_files:
        loc = parse_path(p)
        if not loc:
            continue
        result = await index_from_disk(p, loc, "mimo", conn, indexed.get(p))
        if result == "updated":
            indexed_count += 1

    for p in cc_files:
        loc = parse_cc_path(p)
        if not loc:
            continue
        result = await index_from_disk(p, loc, "cc", conn, indexed.get(p))
        if result == "updated":
            indexed_count += 1

    conn.commit()
    conn.close()
    return {"indexed": indexed_count, "pruned": pruned}


# ═══════════════════════════════════════════════════════════
# MemoryService (port of service.ts)
# ═══════════════════════════════════════════════════════════

@dataclass
class SearchResult:
    path: str
    scope: str
    scope_id: str
    type: str
    snippet: str
    score: float


DEFAULT_SEARCH_SCORE_FLOOR = 0.15
DEFAULT_SEARCH_LIMIT = 10


class MemoryService:
    """High-level memory service with FTS search, reconcile, and path utilities."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(CONFIG_DIR / "memory.db")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def reconcile(self, root: str, cc_base: str | None = None) -> dict[str, int]:
        """Reconcile disk files with the FTS index. Returns {indexed, pruned}."""
        return await reconcile_memory(root, cc_base, self.db_path)

    def search(
        self,
        query: str,
        scope: str | None = None,
        scope_id: str | None = None,
        type_filter: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        score_floor: float = DEFAULT_SEARCH_SCORE_FLOOR,
    ) -> list[SearchResult]:
        """Search memory entries with FTS5, filtered by scope/type.

        Uses OR-join for high recall, then applies a relative score floor
        to drop common-word-only noise. The top result is always kept.
        """
        fts_query = build_fts_query(query)
        if not fts_query:
            return []

        conn = self._connect()

        # Build WHERE conditions
        conditions: list[str] = []
        params: list[str | int] = []
        if scope:
            conditions.append("m.scope = ?")
            params.append(scope)
        if scope_id:
            conditions.append("m.scope_id = ?")
            params.append(scope_id)
        if type_filter:
            conditions.append("m.type = ?")
            params.append(type_filter)

        where_clause = f"AND {' AND '.join(conditions)}" if conditions else ""

        # Over-fetch (3x, capped) so the relative floor can trim noise
        fetch_limit = min(limit * 3, 50)
        params.append(fts_query)
        params.append(fetch_limit)

        sql = f"""
            SELECT m.id, m.path, m.scope, m.scope_id, m.type,
                   snippet(memory_fts_idx, 0, '<<', '>>', '...', 32) AS snippet,
                   bm25(memory_fts_idx) AS score
            FROM memory_fts_idx
            JOIN memory_entries m ON m.rowid = memory_fts_idx.rowid
            WHERE memory_fts_idx MATCH ?
            {where_clause}
            ORDER BY score
            LIMIT ?
        """

        try:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

            # FTS5 bm25() returns lower = better; convert to higher = better for caller
            mapped: list[SearchResult] = []
            for r in rows:
                mapped.append(SearchResult(
                    path=r["path"],
                    scope=r["scope"],
                    scope_id=r["scope_id"],
                    type=r["type"],
                    snippet=r["snippet"],
                    score=-r["score"],
                ))
        except sqlite3.OperationalError:
            # Fallback: LIKE-based search if FTS5 is not available
            cursor = conn.execute(
                f"SELECT id, path, scope, scope_id, type, substr(content, 1, 200) AS snippet, 0.0 AS score "
                f"FROM memory_entries WHERE content LIKE ? {where_clause.replace('AND', 'AND', 1).replace('AND', 'AND') if where_clause else ''} "
                f"ORDER BY created_at DESC LIMIT ?",
                [f"%{query}%"] + params[:-1] + [fetch_limit],
            )
            rows = cursor.fetchall()
            mapped = []
            for r in rows:
                mapped.append(SearchResult(
                    path=r["path"],
                    scope=r["scope"],
                    scope_id=r["scope_id"],
                    type=r["type"],
                    snippet=r["snippet"],
                    score=0.0,
                ))
        finally:
            conn.close()

        if not mapped:
            return []

        # Apply relative score floor
        top_score = mapped[0].score
        cutoff = top_score * score_floor if score_floor > 0 else float("-inf")

        result: list[SearchResult] = []
        for i, r in enumerate(mapped):
            if i == 0 or r.score >= cutoff:
                result.append(r)
                if len(result) >= limit:
                    break

        return result


# ═══════════════════════════════════════════════════════════
# 原有 MemoryStore（保留完整兼容）
# ═══════════════════════════════════════════════════════════


class MemoryStore:
    """原有记忆存储类 — 保持向后兼容。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(CONFIG_DIR / "memory.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init()

    def _init(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY, path TEXT NOT NULL DEFAULT '',
                scope TEXT NOT NULL DEFAULT 'project', scope_id TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT 'note', content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}', created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mem_scope ON memory_entries(scope, scope_id);
            CREATE INDEX IF NOT EXISTS idx_mem_type ON memory_entries(type);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts_idx USING fts5(
                content, path, scope, scope_id, type, content=memory_entries, content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memory_entries BEGIN
                INSERT INTO memory_fts_idx(rowid, content, path, scope, scope_id, type)
                VALUES (new.rowid, new.content, new.path, new.scope, new.scope_id, new.type);
            END;
            CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memory_entries BEGIN
                INSERT INTO memory_fts_idx(memory_fts_idx, rowid, content, path, scope, scope_id, type)
                VALUES ('delete', old.rowid, old.content, old.path, old.scope, old.scope_id, old.type);
            END;
        """)
        self._conn.commit()

    def add(self, content: str, path: str = "", scope: str = "project", scope_id: str = "", type: str = "note") -> str:
        mem_id = uuid.uuid4().hex[:16]
        now = time.time()
        self._conn.execute(
            "INSERT INTO memory_entries VALUES (?,?,?,?,?,?,?,?,?)",
            (mem_id, path, scope, scope_id, type, content, "{}", now, now),
        )
        self._conn.commit()
        return mem_id

    def search(self, query: str, limit: int = 10) -> list[dict]:
        tokens = re.findall(r"[a-zA-Z0-9_]+", query)
        if not tokens:
            cursor = self._conn.execute(
                "SELECT id, path, scope, scope_id, type, substr(content,1,200) AS snippet "
                "FROM memory_entries WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", min(limit * 3, 50)),
            )
            rows = cursor.fetchall()
            if not rows:
                return []
            return [{"id": r[0], "path": r[1], "scope": r[2], "scope_id": r[3],
                     "type": r[4], "snippet": r[5], "score": 1.0} for r in rows][:limit]
        fts = " OR ".join(f'"{t}"' for t in tokens)
        cursor = self._conn.execute("""
            SELECT m.id, m.path, m.scope, m.scope_id, m.type,
                   snippet(memory_fts_idx, 0, '<<', '>>', '...', 32) AS snippet,
                   bm25(memory_fts_idx, 0.0, 0.0, 0.0, 0.0, 1.0) AS score
            FROM memory_fts_idx
            JOIN memory_entries m ON m.rowid = memory_fts_idx.rowid
            WHERE memory_fts_idx MATCH ? ORDER BY score LIMIT ?
        """, (fts, min(limit * 3, 50)))
        rows = cursor.fetchall()
        if not rows:
            return []
        mapped = [{"id": r[0], "path": r[1], "scope": r[2], "scope_id": r[3], "type": r[4],
                   "snippet": r[5], "score": -r[6]} for r in rows]
        top = mapped[0]["score"]
        return [m for i, m in enumerate(mapped) if i == 0 or m["score"] >= top * 0.15][:limit]

    def list(self, limit: int = 50) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT id, type, substr(content,1,200) FROM memory_entries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [{"id": r[0], "type": r[1], "content": r[2]} for r in cursor]

    def delete(self, mem_id: str) -> bool:
        c = self._conn.execute("DELETE FROM memory_entries WHERE id=?", (mem_id,))
        self._conn.commit()
        return c.rowcount > 0

    def close(self):
        self._conn.close()


# Singleton instances
memory = MemoryStore()
service = MemoryService()
