"""
Skill 系统 — 移植自 packages/opencode/src/skill/
可复用的自动化工作流：知识提取、压缩、Dream/Distill

维护现有 SkillManager API 的同时补充 MiMo-Code 的完整功能：
- localized_alias(): 多语言别名
- search_skills(): BM25 搜索
- skill discovery / disk scanning
- builtin / compose bundle extraction
"""

from __future__ import annotations

import json
import logging
import math
import os
import pathlib
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from craft.config import CONFIG_DIR

logger = logging.getLogger(__name__)

SKILL_DB = CONFIG_DIR / "skills.json"


# ═══════════════════════════════════════════════════════════
# 原有 API（保留兼容）
# ═══════════════════════════════════════════════════════════


class SkillStep:
    def __init__(self, name: str, agent_id: str = "build", prompt: str = "",
                 input_key: str = "", output_key: str = "",
                 max_tokens: int = 4096, temperature: float = 0.3):
        self.name = name
        self.agent_id = agent_id
        self.prompt = prompt
        self.input_key = input_key
        self.output_key = output_key
        self.max_tokens = max_tokens
        self.temperature = temperature


class Skill:
    def __init__(self, name: str, description: str = "", version: str = "1.0.0"):
        self.id = f"skill_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.description = description
        self.version = version
        self.steps: list[SkillStep] = []
        self.input_schema: dict = {}
        self.output_schema: dict = {}
        self.author: str = ""
        self.tags: list[str] = []
        self.created_at = time.time()

    def add_step(self, step: SkillStep):
        self.steps.append(step)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "version": self.version, "steps": [s.__dict__ for s in self.steps],
            "author": self.author, "tags": self.tags,
            "created_at": self.created_at,
        }


# ═══════════════════════════════════════════════════════════
# MiMo-Code 移植：Skill Info 数据类 / 搜索 / 别名
# ═══════════════════════════════════════════════════════════

@dataclass
class SkillInfo:
    """A skill as defined by MiMo-Code's Info schema."""
    name: str
    description: str
    location: str
    content: str = ""
    aliases: list[str] = field(default_factory=list)
    hidden: bool = False
    bundled: bool = False


# ── 多语言别名 (port of localized-alias.ts) ──

# Simplified: in production, load from locale dictionaries.
_localized_aliases_cache: dict[str, list[str]] = {}


def localized_alias(skill: SkillInfo) -> list[str]:
    """Get localized aliases for a skill from available i18n dictionaries."""
    if not skill.bundled or skill.name.startswith("compose:"):
        return []
    return _localized_aliases_cache.get(skill.name, [])


def register_localized_alias(skill_name: str, *aliases: str):
    """Register localized aliases for a skill."""
    if skill_name not in _localized_aliases_cache:
        _localized_aliases_cache[skill_name] = []
    for alias in aliases:
        alias = alias.strip()
        if alias:
            _localized_aliases_cache[skill_name].append(alias)


# ── BM25 搜索 (port of search.ts) ──

# Stop words: query-structure labels stripped alongside common words
STOP_WORDS: set[str] = {
    "a", "action", "an", "and", "audience",
    "for", "from", "input", "of", "output",
    "the", "to", "with",
}

# BM25 parameters (from Flags in MiMo-Code)
STEMMING_MIN_LENGTH = 4
BM25_K1 = 1.5
BM25_B = 0.75
BM25_IDF_SMOOTHING = 0.5
EXACT_SCORE = 2.0
BM25_SCORE_WEIGHT = 1.5
QUERY_COVERAGE_WEIGHT = 0.5
SCORE_PRECISION = 3
MAX_RESULTS = 10


@dataclass
class SearchResult:
    skill_id: str
    name: str
    score: float
    reason: str


def _normalize(value: str) -> str:
    return value.lower().strip()


def _explicitly_mentions(query: str, value: str) -> bool:
    """Check if query explicitly mentions a value (exact or CJK sub-match)."""
    nq = _normalize(query)
    nv = _normalize(value)
    if nq == nv:
        return True
    # Check if value contains CJK and query includes it
    if any('\u4e00' <= c <= '\u9fff' for c in nv):
        return nq in nv or nv in nq
    # Word-boundary match for non-CJK
    escaped = re.escape(nv)
    return bool(re.search(
        rf"(^|[^\w]){escaped}($|[^\w])",
        nq,
        re.UNICODE,
    ))


def _tokenize(value: str) -> list[str]:
    """Tokenize a string into search tokens with simple stemming."""
    result: list[str] = []
    nv = _normalize(value)

    # Insert spaces around CJK characters
    nv = re.sub(r"([\u4e00-\u9fff]+)", r" \1 ", nv)

    for token in re.split(r"[^\w]+", nv):
        if not token or token in STOP_WORDS:
            continue
        # Simple stemming: remove trailing 's' for non-CJK tokens
        if not any('\u4e00' <= c <= '\u9fff' for c in token):
            if len(token) > STEMMING_MIN_LENGTH and token.endswith("s") and not token.endswith("ss"):
                token = token[:-1]
        result.append(token)
    return result


def search_skills(query: str, skills: list[SkillInfo]) -> list[SearchResult]:
    """Search skills by BM25 relevance scoring.

    Returns results ordered by relevance, with exact name/alias matches boosted.
    """
    # Filter out compose: skills from search
    searchable = [s for s in skills if not s.name.startswith("compose:")]

    # Exact matches
    exact: list[SearchResult] = []
    for skill in searchable:
        candidates = [skill.name] + (skill.aliases or []) + localized_alias(skill)
        for value in candidates:
            if _explicitly_mentions(query, value):
                exact.append(SearchResult(
                    skill_id=skill.name,
                    name=skill.name,
                    score=EXACT_SCORE,
                    reason=f"The query explicitly mentions the skill ID, name, or alias for {skill.name}.",
                ))
                break

    # BM25 scoring
    query_tokens = list(set(_tokenize(query)))
    if not query_tokens:
        return exact[:MAX_RESULTS]

    documents: list[list[str]] = []
    for skill in searchable:
        text = " ".join(
            [skill.name]
            + (skill.aliases or [])
            + localized_alias(skill)
            + [skill.description]
        )
        documents.append(_tokenize(text))

    # Average document length for BM25 length normalization
    avg_length = sum(len(d) for d in documents) / max(len(documents), 1)

    bm25_scores: list[float] = []
    for doc in documents:
        score = 0.0
        doc_len = len(doc)
        for token in query_tokens:
            freq = doc.count(token)
            if freq == 0:
                continue
            doc_freq = sum(1 for d in documents if token in d)
            idf = math.log(
                1 + (len(documents) - doc_freq + BM25_IDF_SMOOTHING) / (doc_freq + BM25_IDF_SMOOTHING)
            )
            score += idf * (
                (freq * (BM25_K1 + 1)) / (freq + BM25_K1 * (1 - BM25_B + BM25_B * (doc_len / avg_length)))
            )
        bm25_scores.append(score)

    max_score = max(bm25_scores) if bm25_scores else 0.0

    bm25_results: list[SearchResult] = []
    for i, skill in enumerate(searchable):
        if bm25_scores[i] <= 0:
            continue
        coverage = sum(1 for t in query_tokens if t in documents[i]) / max(len(query_tokens), 1)
        normalized_score = (
            (bm25_scores[i] / max_score) * BM25_SCORE_WEIGHT + coverage * QUERY_COVERAGE_WEIGHT
        )
        # Describe matched terms
        matched_terms = [t for t in query_tokens if t in _tokenize(skill.description)]
        reason = f"The skill description matches these query terms: {', '.join(matched_terms)}." if matched_terms else "Relevance match."
        bm25_results.append(SearchResult(
            skill_id=skill.name,
            name=skill.name,
            score=round(normalized_score, SCORE_PRECISION),
            reason=reason,
        ))

    # Sort BM25 results by score descending, then name ascending
    bm25_results.sort(key=lambda r: (-r.score, r.name))

    # Merge: exact first, then BM25 (deduplicated)
    exact_ids = {r.skill_id for r in exact}
    merged = list(exact)
    for r in bm25_results:
        if r.skill_id not in exact_ids:
            merged.append(r)
            if len(merged) >= MAX_RESULTS:
                break

    return merged[:MAX_RESULTS]


# ═══════════════════════════════════════════════════════════
# Skill Discovery — 磁盘扫描与加载
# ═══════════════════════════════════════════════════════════

# Directories to scan for external skills
EXTERNAL_DIRS = [".claude", ".agents", ".codex", ".opencode"]
EXTERNAL_SKILL_PATTERN = "skills/**/SKILL.md"
SKILL_PATTERN = "**/SKILL.md"


def discover_skill_files(root_dirs: list[str]) -> list[str]:
    """Scan directories for SKILL.md files.

    Returns a list of absolute paths to discovered SKILL.md files.
    """
    matches: set[str] = set()
    for root in root_dirs:
        root_path = Path(root).expanduser()
        if not root_path.exists():
            continue
        # Recursive glob for SKILL.md
        for p in root_path.rglob("SKILL.md"):
            matches.add(str(p.absolute()))
    return sorted(matches)


def parse_markdown_skill(file_path: str) -> SkillInfo | None:
    """Parse a SKILL.md file and return a SkillInfo.

    Expects YAML frontmatter with at least `name` and `description`.
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception:
        logger.warning("Failed to read skill file: %s", file_path)
        return None

    # Parse YAML frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not fm_match:
        logger.warning("Skill file missing frontmatter: %s", file_path)
        return None

    import yaml
    try:
        frontmatter = yaml.safe_load(fm_match.group(1))
    except Exception as e:
        logger.warning("Failed to parse skill frontmatter: %s: %s", file_path, e)
        return None

    if not isinstance(frontmatter, dict):
        return None

    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    aliases = frontmatter.get("aliases", [])
    hidden = frontmatter.get("hidden", False)

    if not name or not description:
        logger.warning("Skill missing name or description: %s", file_path)
        return None

    return SkillInfo(
        name=name,
        description=description,
        location=file_path,
        content=content,
        aliases=aliases if isinstance(aliases, list) else [],
        hidden=bool(hidden),
    )


# ═══════════════════════════════════════════════════════════
# Builtin / Compose Bundle extraction
# ═══════════════════════════════════════════════════════════

BUILTIN_SKILL_DIR = CONFIG_DIR / "builtin_skills"
COMPOSE_SKILL_DIR = CONFIG_DIR / "compose_skills"


def extract_builtin_bundle() -> str | None:
    """Extract built-in skills to disk. Returns the root directory."""
    root = BUILTIN_SKILL_DIR
    root.mkdir(parents=True, exist_ok=True)

    # Built-in skill definitions (inlined from bundle.macro)
    builtin_skills: dict[str, dict[str, str]] = {
        "filesystem": {
            "SKILL.md": "---\nname: filesystem\ndescription: Read, write, edit, search files and directories\n---\n",
        },
        "code-analysis": {
            "SKILL.md": "---\nname: code-analysis\ndescription: Analyze code structure, dependencies, and patterns\naliases: [code-review, code-inspect]\n---\n",
        },
        "web-research": {
            "SKILL.md": "---\nname: web-research\ndescription: Search the web, fetch pages, extract content\naliases: [search, browse]\n---\n",
        },
        "database": {
            "SKILL.md": "---\nname: database\ndescription: Query databases, run migrations, manage data\naliases: [db, sql]\n---\n",
        },
        "devops": {
            "SKILL.md": "---\nname: devops\ndescription: Manage deployments, infrastructure, CI/CD pipelines\naliases: [deploy, infra]\n---\n",
        },
        "testing": {
            "SKILL.md": "---\nname: testing\ndescription: Run tests, analyze coverage, generate test cases\naliases: [test, pytest]\n---\n",
        },
    }

    for skill_name, files in builtin_skills.items():
        skill_dir = root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        for rel_path, content in files.items():
            (skill_dir / rel_path).write_text(content, encoding="utf-8")

    return str(root)


def extract_compose_bundle() -> str | None:
    """Extract compose skills to disk. Returns the root directory."""
    root = COMPOSE_SKILL_DIR
    root.mkdir(parents=True, exist_ok=True)

    compose_skills: dict[str, dict[str, str]] = {
        "compose:extract-knowledge": {
            "SKILL.md": "---\nname: compose:extract-knowledge\ndescription: Extract structured knowledge from free-form text\n---\n",
        },
        "compose:summarize": {
            "SKILL.md": "---\nname: compose:summarize\ndescription: Compose a concise summary from long documents\n---\n",
        },
    }

    for skill_name, files in compose_skills.items():
        skill_dir = root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        for rel_path, content in files.items():
            (skill_dir / rel_path).write_text(content, encoding="utf-8")

    return str(root)


# ═══════════════════════════════════════════════════════════
# SkillManager（原有 + 新功能）
# ═══════════════════════════════════════════════════════════


class SkillManager:
    """技能管理器 — 保留原有 API 并添加 MiMo-Code 功能。"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}           # old API: id → Skill
        self._skill_infos: dict[str, SkillInfo] = {}  # new API: name → SkillInfo
        self._load()
        self._register_builtin()

    # ── 原有 API ──

    def _load(self):
        try:
            if SKILL_DB.exists():
                data = json.loads(SKILL_DB.read_text())
                for item in data:
                    skill = Skill("")
                    skill.__dict__.update(item)
                    self._skills[skill.id] = skill
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SKILL_DB.write_text(json.dumps(
            [s.to_dict() for s in self._skills.values()], indent=2, default=str
        ))

    def _register_builtin(self):
        """内置 Skill：Dream（知识提取）、Distill（知识压缩）"""
        dream = Skill("dream", "从对话中提取知识存入记忆", version="1.0.0")
        dream.add_step(SkillStep("extract", "build", "从以下对话中提取关键知识、决策和洞见，以简洁的格式输出。"))
        dream.add_step(SkillStep("store", "build", "将提取的知识存入记忆系统。"))
        self.add(dream, builtin=True)

        distill = Skill("distill", "压缩和重组知识", version="1.0.0")
        distill.add_step(SkillStep("analyze", "plan", "分析以下内容，提取核心概念和关系。"))
        distill.add_step(SkillStep("synthesize", "build", "将分析结果压缩为清晰的摘要。"))
        distill.tags = ["knowledge", "compress"]
        self.add(distill, builtin=True)

        code_review = Skill("code-review", "代码审查", version="1.0.0")
        code_review.add_step(SkillStep("analyze", "plan", "审查以下代码，指出问题。"))
        code_review.add_step(SkillStep("fix", "build", "修复发现的问题。"))
        code_review.tags = ["code", "review"]
        self.add(code_review, builtin=True)

    def add(self, skill: Skill, builtin: bool = False) -> str:
        self._skills[skill.id] = skill
        if not builtin:
            self._save()
        return skill.id

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list(self, tag: str | None = None) -> list[dict]:
        skills = self._skills.values()
        if tag:
            skills = [s for s in skills if tag in s.tags]
        return [s.to_dict() for s in skills]

    def delete(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            del self._skills[skill_id]
            self._save()
            return True
        return False

    # ── 新 API: SkillInfo 管理 (MiMo-Code 兼容) ──

    def reload(self):
        """Reload skills from disk (scan all skill directories)."""
        self._skill_infos.clear()
        self._load_skill_infos()
        logger.info("Reloaded %d skills from disk", len(self._skill_infos))

    def _load_skill_infos(self):
        """Scan all skill directories and load SKILL.md files."""
        # Built-in skills
        builtin_root = extract_builtin_bundle()
        if builtin_root:
            for file_path in discover_skill_files([builtin_root]):
                info = parse_markdown_skill(file_path)
                if info:
                    info.bundled = True
                    if info.name not in self._skill_infos:
                        self._skill_infos[info.name] = info

        # External skill directories
        external_dirs = [
            os.path.expanduser("~/.claude"),
            os.path.expanduser("~/.agents"),
            os.path.expanduser("~/.codex"),
            os.path.expanduser("~/.opencode"),
        ]
        external_dirs = [d for d in external_dirs if Path(d).exists()]

        for file_path in discover_skill_files(external_dirs):
            info = parse_markdown_skill(file_path)
            if info:
                # User skills override bundled
                if info.name in self._skill_infos and self._skill_infos[info.name].bundled:
                    logger.info("User skill overrides bundled: %s", info.name)
                self._skill_infos[info.name] = info

        # Project-level external skills (scan current directory upward)
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            for ext_dir in EXTERNAL_DIRS:
                candidate = parent / ext_dir
                if candidate.exists():
                    for file_path in discover_skill_files([str(candidate)]):
                        info = parse_markdown_skill(file_path)
                        if info:
                            if info.name in self._skill_infos and self._skill_infos[info.name].bundled:
                                pass  # already overridden
                            self._skill_infos[info.name] = info

        # Also register builtin skills from the old Skill objects as SkillInfo
        for skill in self._skills.values():
            if skill.name not in self._skill_infos:
                self._skill_infos[skill.name] = SkillInfo(
                    name=skill.name,
                    description=skill.description,
                    location="",
                    content=skill.to_dict(),
                    bundled=True,
                    aliases=[],
                )

    def all(self) -> list[SkillInfo]:
        """Get all loaded skills as SkillInfo list."""
        if not self._skill_infos:
            self._load_skill_infos()
        return list(self._skill_infos.values())

    def get_by_name(self, name: str) -> SkillInfo | None:
        """Get a skill by name (as SkillInfo)."""
        if not self._skill_infos:
            self._load_skill_infos()
        return self._skill_infos.get(name)

    def available(self, agent_permission: list | None = None) -> list[SkillInfo]:
        """Get skills available to a given agent permission context."""
        all_skills = self.all()
        if not agent_permission:
            return sorted(all_skills, key=lambda s: s.name)

        from craft.core.permission import evaluate as perm_evaluate, Rule
        result: list[SkillInfo] = []
        for skill in all_skills:
            r = perm_evaluate("skill", skill.name, agent_permission)
            if r.action != "deny":
                result.append(skill)
        return sorted(result, key=lambda s: s.name)

    def search(self, query: str) -> list[SearchResult]:
        """Search skills using BM25."""
        all_skills = self.all()
        return search_skills(query, all_skills)


# Module-level singleton
skills = SkillManager()

# Initialize skill infos on import
skills.reload()
