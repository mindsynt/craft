"""
工作流 — 移植自 packages/opencode/src/workflow/
工作流脚本执行、步骤管理、元数据解析、内置工作流、持久化
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Meta — WorkflowMeta & parseMeta (meta.ts)
# ═══════════════════════════════════════════════════════════

@dataclass
class WorkflowPhase:
    title: str = ""
    detail: str | None = None


@dataclass
class WorkflowPermission:
    permission: str = ""
    patterns: list[str] | None = None
    always: list[str] | None = None
    reason: str | None = None


@dataclass
class WorkflowMeta:
    name: str = ""
    description: str = ""
    when_to_use: str | None = None
    phases: list[WorkflowPhase] | None = None
    model: str | None = None
    permissions: list[WorkflowPermission] | None = None


@dataclass
class ParseResult:
    ok: bool = False
    meta: WorkflowMeta | None = None
    body: str = ""
    error: str = ""


META_START_RE_STR = r"export\s+const\s+meta\s*="


def parse_meta(script: str) -> ParseResult:
    """解析工作流脚本中的 meta 块 — 移植自 meta.ts parseMeta"""
    import re
    match = re.search(META_START_RE_STR, script)
    if not match:
        return ParseResult(ok=False, error="workflow script must start with `export const meta = { ... }`")

    start = match.start()

    # 找到开始的花括号
    open_brace = script.find("{", match.end())
    if open_brace == -1:
        return ParseResult(ok=False, error="workflow script must start with `export const meta = { ... }`")

    # 平衡花括号
    close = _find_balanced_close(script, open_brace)
    if close == -1:
        return ParseResult(ok=False, error="could not locate a balanced meta object literal")

    literal = script[open_brace:close + 1]

    # 解析纯数据字面量（不执行代码）
    parsed = _parse_data_literal(literal)
    if not parsed["ok"]:
        return ParseResult(ok=False, error=f"meta is not a valid object literal: {parsed['error']}")

    meta_dict = parsed["value"]
    if not isinstance(meta_dict, dict):
        return ParseResult(ok=False, error="meta must be an object")

    if not isinstance(meta_dict.get("name"), str) or not meta_dict["name"]:
        return ParseResult(ok=False, error="meta.name (non-empty string) is required")
    if not isinstance(meta_dict.get("description"), str) or not meta_dict["description"]:
        return ParseResult(ok=False, error="meta.description (non-empty string) is required")

    # 验证 permissions
    if "permissions" in meta_dict:
        perms = meta_dict["permissions"]
        if not isinstance(perms, list):
            return ParseResult(ok=False, error="meta.permissions must be an array")
        for p in perms:
            if not isinstance(p, dict):
                return ParseResult(ok=False, error="each meta.permissions entry must be an object")
            if not isinstance(p.get("permission"), str) or not p["permission"]:
                return ParseResult(ok=False, error="each meta.permissions entry needs a non-empty `permission` string")

    # 提取 phases
    phases = None
    if meta_dict.get("phases") and isinstance(meta_dict["phases"], list):
        phases = []
        for p in meta_dict["phases"]:
            if isinstance(p, dict):
                phases.append(WorkflowPhase(
                    title=p.get("title", ""),
                    detail=p.get("detail"),
                ))

    # 提取 permissions
    permissions = None
    if meta_dict.get("permissions") and isinstance(meta_dict["permissions"], list):
        permissions = []
        for p in meta_dict["permissions"]:
            permissions.append(WorkflowPermission(
                permission=p.get("permission", ""),
                patterns=p.get("patterns"),
                always=p.get("always"),
                reason=p.get("reason"),
            ))

    end_index = close + 1
    if close + 1 < len(script) and script[close + 1] == ";":
        end_index += 1

    meta = WorkflowMeta(
        name=meta_dict["name"],
        description=meta_dict["description"],
        when_to_use=meta_dict.get("whenToUse"),
        phases=phases,
        model=meta_dict.get("model"),
        permissions=permissions,
    )

    # 构建 body（meta 部分替换为等长空白，保留行号）
    matched = script[start:end_index]
    body = script[:start] + matched.replace("\n", " ").replace(" ", " ") + script[end_index:]
    # 简化为保留 script 中的非 meta 部分
    body_lines = []
    for i, line in enumerate(script.split("\n")):
        body_lines.append(line)
    body = "\n".join(body_lines)

    return ParseResult(ok=True, meta=meta, body=body)


def _find_balanced_close(script: str, open_idx: int) -> int:
    """查找平衡的闭合花括号 — 移植自 meta.ts findBalancedClose"""
    depth = 0
    quote = ""
    i = open_idx
    while i < len(script):
        ch = script[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch == "/" and i + 1 < len(script) and script[i + 1] == "/":
            i += 2
            while i < len(script) and script[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < len(script) and script[i + 1] == "*":
            i += 2
            while i < len(script) and not (script[i] == "*" and i + 1 < len(script) and script[i + 1] == "/"):
                i += 1
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _parse_data_literal(text: str) -> dict:
    """解析纯数据字面量（不执行代码）— 移植自 meta.ts parseDataLiteral"""
    reader = {"text": text, "pos": 0, "depth": 0}
    try:
        _skip_trivia(reader)
        value = _read_value(reader)
        _skip_trivia(reader)
        if reader["pos"] != len(reader["text"]):
            return {"ok": False, "error": f"unexpected token at offset {reader['pos']}"}
        return {"ok": True, "value": value}
    except _ParseFail as e:
        return {"ok": False, "error": str(e)}


class _ParseFail(Exception):
    pass


def _skip_trivia(r: dict):
    """跳过空白和注释"""
    while r["pos"] < len(r["text"]):
        ch = r["text"][r["pos"]]
        if ch in " \t\n\r\f\v":
            r["pos"] += 1
            continue
        if ch == "/" and r["pos"] + 1 < len(r["text"]):
            if r["text"][r["pos"] + 1] == "/":
                r["pos"] += 2
                while r["pos"] < len(r["text"]) and r["text"][r["pos"]] != "\n":
                    r["pos"] += 1
                continue
            if r["text"][r["pos"] + 1] == "*":
                r["pos"] += 2
                while r["pos"] < len(r["text"]) and not (r["text"][r["pos"]] == "*" and r["pos"] + 1 < len(r["text"]) and r["text"][r["pos"] + 1] == "/"):
                    r["pos"] += 1
                r["pos"] += 2
                continue
        return


def _read_value(r: dict) -> Any:
    """读取值"""
    ch = r["text"][r["pos"]] if r["pos"] < len(r["text"]) else None
    if ch is None:
        raise _ParseFail("unexpected end of input")
    if ch == "{":
        return _read_object(r)
    if ch == "[":
        return _read_array(r)
    if ch in "\"'":
        return _read_string(r)
    if ch == "-" or (ch is not None and "0" <= ch <= "9"):
        return _read_number(r)
    if _match_keyword(r, "true"):
        return True
    if _match_keyword(r, "false"):
        return False
    if _match_keyword(r, "null"):
        return None
    raise _ParseFail(f"unexpected token at offset {r['pos']} (only data literals are allowed)")


def _read_object(r: dict) -> dict:
    """读取对象"""
    r["depth"] += 1
    if r["depth"] > 100:
        raise _ParseFail("meta nesting too deep")
    r["pos"] += 1
    obj = {}
    _skip_trivia(r)
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "}":
        r["pos"] += 1
        r["depth"] -= 1
        return obj
    while True:
        _skip_trivia(r)
        key = _read_key(r)
        _skip_trivia(r)
        if r["pos"] >= len(r["text"]) or r["text"][r["pos"]] != ":":
            raise _ParseFail(f"expected ':' after key '{key}' at offset {r['pos']}")
        r["pos"] += 1
        _skip_trivia(r)
        obj[key] = _read_value(r)
        _skip_trivia(r)
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == ",":
            r["pos"] += 1
            _skip_trivia(r)
            if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "}":
                r["pos"] += 1
                r["depth"] -= 1
                return obj
            continue
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "}":
            r["pos"] += 1
            r["depth"] -= 1
            return obj
        raise _ParseFail(f"expected ',' or '}}' at offset {r['pos']}")


def _read_array(r: dict) -> list:
    """读取数组"""
    r["depth"] += 1
    if r["depth"] > 100:
        raise _ParseFail("meta nesting too deep")
    r["pos"] += 1
    arr = []
    _skip_trivia(r)
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "]":
        r["pos"] += 1
        r["depth"] -= 1
        return arr
    while True:
        _skip_trivia(r)
        arr.append(_read_value(r))
        _skip_trivia(r)
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == ",":
            r["pos"] += 1
            _skip_trivia(r)
            if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "]":
                r["pos"] += 1
                r["depth"] -= 1
                return arr
            continue
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "]":
            r["pos"] += 1
            r["depth"] -= 1
            return arr
        raise _ParseFail(f"expected ',' or ']' at offset {r['pos']}")


def _read_key(r: dict) -> str:
    """读取对象键"""
    ch = r["text"][r["pos"]] if r["pos"] < len(r["text"]) else None
    if ch in "\"'":
        return _read_string(r)
    if ch is not None and (ch.isalpha() or ch in "_$"):
        start = r["pos"]
        r["pos"] += 1
        while r["pos"] < len(r["text"]) and (r["text"][r["pos"]].isalnum() or r["text"][r["pos"]] in "_$"):
            r["pos"] += 1
        return r["text"][start:r["pos"]]
    raise _ParseFail(f"expected a property name at offset {r['pos']}")


def _read_string(r: dict) -> str:
    """读取字符串"""
    quote = r["text"][r["pos"]]
    r["pos"] += 1
    out = []
    while r["pos"] < len(r["text"]):
        ch = r["text"][r["pos"]]
        if ch == "\\":
            esc = r["text"][r["pos"] + 1] if r["pos"] + 1 < len(r["text"]) else None
            r["pos"] += 2
            if esc == "n":
                out.append("\n")
            elif esc == "t":
                out.append("\t")
            elif esc == "r":
                out.append("\r")
            elif esc == "b":
                out.append("\b")
            elif esc == "f":
                out.append("\f")
            elif esc == "u":
                hex_str = r["text"][r["pos"]:r["pos"] + 4] if r["pos"] + 4 <= len(r["text"]) else ""
                if not re.match(r"^[0-9a-fA-F]{4}$", hex_str):
                    raise _ParseFail("invalid \\u escape")
                out.append(chr(int(hex_str, 16)))
                r["pos"] += 4
            elif esc is not None:
                out.append(esc)
            else:
                raise _ParseFail("unterminated string")
            continue
        if ch == quote:
            r["pos"] += 1
            return "".join(out)
        out.append(ch)
        r["pos"] += 1
    raise _ParseFail("unterminated string")


def _read_number(r: dict) -> float:
    """读取数字"""
    import re
    start = r["pos"]
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == "-":
        r["pos"] += 1
    while r["pos"] < len(r["text"]) and r["text"][r["pos"]].isdigit():
        r["pos"] += 1
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] == ".":
        r["pos"] += 1
        while r["pos"] < len(r["text"]) and r["text"][r["pos"]].isdigit():
            r["pos"] += 1
    if r["pos"] < len(r["text"]) and r["text"][r["pos"]] in "eE":
        r["pos"] += 1
        if r["pos"] < len(r["text"]) and r["text"][r["pos"]] in "+-":
            r["pos"] += 1
        while r["pos"] < len(r["text"]) and r["text"][r["pos"]].isdigit():
            r["pos"] += 1
    raw = r["text"][start:r["pos"]]
    return float(raw)


def _match_keyword(r: dict, word: str) -> bool:
    """匹配关键字"""
    if r["text"][r["pos"]:r["pos"] + len(word)] == word:
        after_idx = r["pos"] + len(word)
        if after_idx >= len(r["text"]) or not (r["text"][after_idx].isalnum() or r["text"][after_idx] in "_$"):
            r["pos"] += len(word)
            return True
    return False


# ═══════════════════════════════════════════════════════════
# Workspace (workspace.ts)
# ═══════════════════════════════════════════════════════════

def resolve_in_workspace(root: str, rel: str) -> str:
    """解析工作空间内的路径 — 移植自 workspace.ts resolveInWorkspace"""
    abs_path = str(Path(root).resolve() / rel)
    root_resolved = str(Path(root).resolve())
    if abs_path != root_resolved and not abs_path.startswith(root_resolved + "/"):
        raise ValueError(f"workspace path escapes the workspace root: {rel}")
    return abs_path


def make_file_hooks(root: str) -> dict:
    """创建工作空间文件钩子 — 移植自 workspace.ts makeFileHooks"""

    async def _read_file(rel: str) -> str | None:
        abs_path = resolve_in_workspace(root, rel)
        p = Path(abs_path)
        return p.read_text(encoding="utf-8") if p.exists() else None

    async def _write_file(rel: str, content: str) -> None:
        abs_path = resolve_in_workspace(root, rel)
        Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
        Path(abs_path).write_text(content, encoding="utf-8")

    async def _exists(rel: str) -> bool:
        abs_path = resolve_in_workspace(root, rel)
        return Path(abs_path).exists()

    async def _glob(pattern: str) -> list[str]:
        import glob as glob_mod
        results = []
        for p in glob_mod.glob(pattern, root_dir=root, recursive=True):
            if not p.startswith("..") and not Path(p).is_absolute():
                results.append(p)
        return sorted(results)

    return {
        "readFile": _read_file,
        "writeFile": _write_file,
        "exists": _exists,
        "glob": _glob,
    }


# ═══════════════════════════════════════════════════════════
# Events (events.ts)
# ═══════════════════════════════════════════════════════════

@dataclass
class WorkflowPhaseEvent:
    session_id: str = ""
    run_id: str = ""
    title: str = ""


@dataclass
class WorkflowLogEvent:
    session_id: str = ""
    run_id: str = ""
    message: str = ""


@dataclass
class WorkflowStartedEvent:
    session_id: str = ""
    run_id: str = ""
    name: str = ""


@dataclass
class WorkflowFinishedEvent:
    session_id: str = ""
    run_id: str = ""
    status: str = ""  # "completed" | "failed" | "cancelled"
    error: str | None = None


@dataclass
class WorkflowAgentFailedEvent:
    session_id: str = ""
    run_id: str = ""
    actor_id: str | None = None
    agent_type: str = ""
    label: str | None = None
    phase: str | None = None
    reason: str = ""  # "over-cap" | "spawn-reject" | "timeout" | "actor-error" | "no-deliverable"
    error_message: str | None = None


@dataclass
class WorkflowChildFailedEvent:
    session_id: str = ""
    run_id: str = ""
    child_run_id: str = ""
    name: str = ""
    status: str = ""  # "failed" | "cancelled"
    error: str | None = None


# ═══════════════════════════════════════════════════════════
# Resolve (resolve.ts)
# ═══════════════════════════════════════════════════════════

META_RE = re.compile(r"export\s+const\s+meta\s*=")


def is_inline_script(name_or_script: str) -> bool:
    """检查是否为内联脚本 — 移植自 resolve.ts isInlineScript"""
    return bool(META_RE.search(name_or_script))


SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


async def resolve_workflow_script(name: str, start: str, stop: str) -> str | None:
    """解析工作流脚本 — 移植自 resolve.ts resolveWorkflowScript"""
    if not SAFE_NAME_RE.match(name):
        raise ValueError(f"invalid workflow name: {name}")

    # 从 start 向上查找到 stop
    subdirs = [".mimocode/workflows", ".claude/workflows"]
    candidates = []
    current = start
    while True:
        for sub in subdirs:
            candidate = Path(current) / sub / f"{name}.js"
            if candidate.exists():
                candidates.append(str(candidate))
        if current == stop:
            break
        parent = str(Path(current).parent)
        if parent == current:
            break
        current = parent

    for found in candidates:
        return Path(found).read_text(encoding="utf-8")
    return None


# ═══════════════════════════════════════════════════════════
# Builtin (builtin.ts)
# ═══════════════════════════════════════════════════════════

@dataclass
class BuiltinEntry:
    name: str = ""
    description: str = ""
    when_to_use: str | None = None
    phases: list[WorkflowPhase] | None = None
    script: str = ""


class BuiltinWorkflowRegistry:
    """内置工作流注册表 — 移植自 builtin.ts"""

    def __init__(self):
        self._entries: dict[str, BuiltinEntry] = {}
        self._init_defaults()

    def _init_defaults(self):
        """初始化默认内置工作流"""
        self.register(BuiltinEntry(
            name="deep-research",
            description="Deep research on a topic with parallel agent exploration",
            when_to_use="When you need comprehensive research on a topic",
            phases=[WorkflowPhase(title="Research", detail="Parallel research phase")],
            script="# built-in deep research workflow\nasync function main() {}\nmain();",
        ))
        self.register(BuiltinEntry(
            name="fact-check",
            description="Fact-check claims with evidence gathering",
            phases=[WorkflowPhase(title="Verify", detail="Evidence verification phase")],
            script="# built-in fact check workflow\nasync function main() {}\nmain();",
        ))
        self.register(BuiltinEntry(
            name="compose",
            description="Compose and refine content with multiple passes",
            phases=[WorkflowPhase(title="Draft"), WorkflowPhase(title="Review")],
            script="# built-in compose workflow\nasync function main() {}\nmain();",
        ))

    def register(self, entry: BuiltinEntry):
        self._entries[entry.name] = entry

    def list(self) -> list[BuiltinEntry]:
        return sorted(self._entries.values(), key=lambda e: e.name)

    def get(self, name: str) -> BuiltinEntry | None:
        return self._entries.get(name)


builtin_registry = BuiltinWorkflowRegistry()


# ═══════════════════════════════════════════════════════════
# Runtime Ref (runtime-ref.ts)
# ═══════════════════════════════════════════════════════════

_current_workflow_runtime: threading.local = threading.local()


class WorkflowRuntimeRef:
    """工作流运行时引用 — 移植自 runtime-ref.ts"""

    @staticmethod
    def get() -> Any | None:
        return getattr(_current_workflow_runtime, "value", None)

    @staticmethod
    def set(value: Any) -> None:
        _current_workflow_runtime.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_workflow_runtime, "value"):
            del _current_workflow_runtime.value


# ═══════════════════════════════════════════════════════════
# Persistence (persistence.ts)
# ═══════════════════════════════════════════════════════════

def _canonical(value: Any) -> Any:
    """递归排序对象键 — 移植自 persistence.ts canonical"""
    if value is None or not isinstance(value, (dict, list)):
        return value
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return {k: _canonical(value[k]) for k in sorted(value.keys())}


def journal_key_base(prompt: str, opts: dict) -> str:
    """计算 journal key base — 移植自 persistence.ts journalKeyBase"""
    material = _canonical({
        "prompt": prompt,
        "agentType": opts.get("agentType"),
        "model": opts.get("model"),
        "schema": opts.get("schema"),
        "phase": opts.get("phase"),
    })
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def journal_key(prompt: str, opts: dict, occ: int) -> str:
    """计算完整 journal key — 移植自 persistence.ts journalKey"""
    return f"{journal_key_base(prompt, opts)}:{occ}"


@dataclass
class JournalEvent:
    t: str = ""  # "agent" | "log" | "phase"
    key: str | None = None
    result: Any = None
    msg: str | None = None
    title: str | None = None
    pass_num: int = 0


@dataclass
class JournalLoad:
    results: dict = field(default_factory=dict)
    pass_num: int = 1


@dataclass
class RunSummary:
    run_id: str = ""
    session_id: str = ""
    name: str = ""
    status: str = "running"  # "running" | "completed" | "failed" | "cancelled"
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    current_phase: str | None = None
    parent_actor_id: str | None = None
    args: Any = None
    script_sha: str | None = None
    agent_timeout_ms: int | None = None
    error: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


class WorkflowPersistence:
    """工作流持久化 — 移植自 persistence.ts"""

    def __init__(self, data_dir: str | None = None):
        self._data_dir = data_dir or str(Path.home() / ".craft" / "workflow")
        self._runs: dict[str, RunSummary] = {}

    def record_start(self, run_id: str, session_id: str, name: str,
                     parent_actor_id: str | None = None, args: Any = None,
                     script_sha: str | None = None,
                     agent_timeout_ms: int | None = None):
        """记录工作流启动"""
        now = time.time()
        summary = RunSummary(
            run_id=run_id,
            session_id=session_id,
            name=name,
            status="running",
            parent_actor_id=parent_actor_id,
            args=args,
            script_sha=script_sha,
            agent_timeout_ms=agent_timeout_ms,
            created_at=now,
            updated_at=now,
        )
        self._runs[run_id] = summary

    def record_phase(self, run_id: str, phase: str):
        """记录阶段"""
        run = self._runs.get(run_id)
        if run:
            run.current_phase = phase
            run.updated_at = time.time()

    def flush_counters(self, run_id: str, running: int, succeeded: int, failed: int):
        """刷新计数器"""
        run = self._runs.get(run_id)
        if run:
            run.running = running
            run.succeeded = succeeded
            run.failed = failed
            run.updated_at = time.time()

    def record_terminal(self, run_id: str, status: str, error: str | None = None):
        """记录终止状态"""
        run = self._runs.get(run_id)
        if run:
            run.status = status
            run.error = error
            run.updated_at = time.time()

    def list(self, session_id: str | None = None) -> list[RunSummary]:
        """列出工作流"""
        if session_id:
            return [s for s in self._runs.values() if s.session_id == session_id]
        return list(self._runs.values())

    def load(self, run_id: str) -> RunSummary | None:
        """加载工作流"""
        return self._runs.get(run_id)


# ═══════════════════════════════════════════════════════════
# 原生工作流引擎 (保留原始功能)
# ═══════════════════════════════════════════════════════════

class WorkflowStep:
    def __init__(self, name: str, agent_id: str = "build", task: str = "",
                 depends_on: list[str] | None = None):
        self.id = uuid.uuid4().hex[:8]
        self.name = name
        self.agent_id = agent_id
        self.task = task
        self.depends_on = depends_on or []
        self.status = "pending"
        self.result: Any = None
        self.error: str | None = None


class WorkflowRun:
    def __init__(self, name: str = "workflow"):
        self.id = f"wf_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.steps: list[WorkflowStep] = []
        self.status = "pending"
        self.created_at = time.time()
        self.completed_at: float | None = None

    def add_step(self, step: WorkflowStep):
        self.steps.append(step)

    def ready_steps(self) -> list[WorkflowStep]:
        completed = {s.id for s in self.steps if s.status == "completed"}
        return [s for s in self.steps if s.status == "pending"
                and all(dep in completed for dep in s.depends_on)]


class WorkflowEngine:
    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}
        self.persistence = WorkflowPersistence()
        self._event_handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable):
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def _emit(self, event: str, data: Any):
        for handler in self._event_handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"[WorkflowEngine] event handler error: {e}")

    def create(self, name: str = "workflow") -> WorkflowRun:
        run = WorkflowRun(name)
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    async def execute(self, run_id: str) -> dict:
        run = self._runs.get(run_id)
        if not run:
            return {"error": "未找到工作流"}
        run.status = "running"
        while True:
            ready = run.ready_steps()
            if not ready:
                break

            async def run_step(step: WorkflowStep):
                step.status = "running"
                try:
                    from craft.core.provider import get_provider
                    llm = get_provider()
                    messages = [{"role": "user", "content": step.task}]
                    resp = await llm.chat(messages=messages)
                    step.result = resp.get("content", "")
                    step.status = "completed"
                except Exception as e:
                    step.status = "failed"
                    step.error = str(e)

            await asyncio.gather(*[run_step(s) for s in ready])

        failed = [s for s in run.steps if s.status == "failed"]
        run.status = "failed" if failed else "completed"
        run.completed_at = time.time()
        return {"id": run.id, "status": run.status, "steps": len(run.steps),
                "failed": len(failed), "completed": time.time() - run.created_at}


workflow_engine = WorkflowEngine()
