"""
权限系统 — 移植自 MiMo-Code packages/opencode/src/permission/
基于规则的权限：允许列表 + 拒绝列表 + 硬限制

维护现有 API 的同时，补充 MiMo-Code 的完整权限模型。
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any


from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# 原有 API（保留兼容）
# ═══════════════════════════════════════════════════════════


class PermissionRule:
    """单条权限规则"""

    ALLOW = "allow"
    DENY = "deny"

    def __init__(self, action: str, target: str = "*", reason: str = ""):
        self.action = action  # allow / deny
        self.target = target  # 工具名或模式
        self.reason = reason

    def matches(self, tool_name: str) -> bool:
        """检查是否匹配此规则"""
        if self.target == "*":
            return True
        if self.target.endswith("*"):
            return tool_name.startswith(self.target[:-1])
        return tool_name == self.target


class Ruleset(BaseModel):
    """权限规则集"""
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)

    def evaluate(self, tool_name: str) -> bool:
        """评估工具是否允许使用"""
        for d in self.deny:
            rule = PermissionRule(PermissionRule.DENY, d)
            if rule.matches(tool_name):
                return False
        for a in self.allow:
            rule = PermissionRule(PermissionRule.ALLOW, a)
            if rule.matches(tool_name):
                return True
        # 默认：只有 allow 列表中有匹配才允许
        return len(self.allow) == 0  # 空列表 = 全部允许


def merge_rulesets(base: Ruleset, overlay: Ruleset | None, hard: Ruleset | None = None) -> Ruleset:
    """合并权限规则：base + overlay，然后追加 hard（不可覆盖）"""
    result = Ruleset(
        allow=list(base.allow),
        deny=list(base.deny),
    )
    if overlay:
        result.allow.extend(overlay.allow)
        result.deny.extend(overlay.deny)
    if hard:
        result.deny.extend(hard.deny)
        result.allow.extend(hard.allow)
    return result


# ═══════════════════════════════════════════════════════════
# MiMo-Code 移植：Rule / evaluate / 通配符匹配
# ═══════════════════════════════════════════════════════════

from craft.core.wildcard import match as wildcard_match


Action = str  # "allow" | "deny" | "ask"
PERMISSION_ACTIONS: tuple[str, ...] = ("allow", "deny", "ask")

# Forced-ask permissions: these always require a human ask,
# even if a wildcard allow rule exists.
FORCED_ASK: set[str] = {"bash_delete"}

# Tool group aliases for permission evaluation
EDIT_TOOLS: set[str] = {"edit", "write", "apply_patch", "multiedit"}


@dataclass
class Rule:
    """A single permission rule (from MiMo-Code schema)."""
    permission: str  # tool name or pattern
    pattern: str     # path pattern
    action: str      # "allow" | "deny" | "ask"


def expand_pattern(pattern: str) -> str:
    """Expand ~ and $HOME in path patterns."""
    if pattern.startswith("~/"):
        return os.path.expanduser("~") + pattern[1:]
    if pattern == "~":
        return os.path.expanduser("~")
    if pattern.startswith("$HOME/"):
        return os.path.expanduser("~") + pattern[5:]
    if pattern.startswith("$HOME"):
        return os.path.expanduser("~") + pattern[5:]
    return pattern


def evaluate(permission: str, pattern: str, *rulesets: list[Rule]) -> Rule:
    """Evaluate a permission+pattern against multiple ordered rulesets.

    findLast semantics: the last matching rule (across all flattened rulesets) wins.
    Returns a default Rule(action='ask') if no rule matches.
    """
    all_rules: list[Rule] = []
    for rs in rulesets:
        all_rules.extend(rs)

    match = None
    for rule in all_rules:
        if wildcard_match(permission, rule.permission) and wildcard_match(pattern, rule.pattern):
            match = rule
    return match if match else Rule(permission=permission, pattern="*", action="ask")


def from_config(config: dict[str, Any]) -> list[Rule]:
    """Convert a config permission dict to a list of Rule objects.

    Input format: {"*": "allow", "write": {"*.py": "deny"}}
    """
    rules: list[Rule] = []
    for key, value in config.items():
        if isinstance(value, str):
            rules.append(Rule(permission=key, action=value, pattern="*"))
        elif isinstance(value, dict):
            for pattern, action in value.items():
                rules.append(Rule(permission=key, pattern=expand_pattern(pattern), action=action))
    return rules


def merge_rules(*rulesets: list[Rule]) -> list[Rule]:
    """Merge multiple rulesets into one flat list."""
    result: list[Rule] = []
    for rs in rulesets:
        result.extend(rs)
    return result


def disabled_tools(tools: list[str], ruleset: list[Rule]) -> set[str]:
    """Find tools that are disabled (deny with pattern '*') by the ruleset.

    Also checks the "edit" group alias for edit-family tools.
    """
    result: set[str] = set()
    for tool in tools:
        rule = None
        for r in ruleset:
            if wildcard_match(tool, r.permission) or (tool in EDIT_TOOLS and wildcard_match("edit", r.permission)):
                rule = r
        if rule and rule.pattern == "*" and rule.action == "deny":
            result.add(tool)
    return result


# ═══════════════════════════════════════════════════════════
# Arity — 命令前缀 arity 检测
# ═══════════════════════════════════════════════════════════

# Generated arity dictionary: command prefix → token count for the "human-understandable command"
ARITY: dict[str, int] = {
    "cat": 1,
    "cd": 1,
    "chmod": 1,
    "chown": 1,
    "cp": 1,
    "echo": 1,
    "env": 1,
    "export": 1,
    "grep": 1,
    "kill": 1,
    "killall": 1,
    "ln": 1,
    "ls": 1,
    "mkdir": 1,
    "mv": 1,
    "ps": 1,
    "pwd": 1,
    "rm": 1,
    "rmdir": 1,
    "sleep": 1,
    "source": 1,
    "tail": 1,
    "touch": 1,
    "unset": 1,
    "which": 1,
    "aws": 3,
    "az": 3,
    "bazel": 2,
    "brew": 2,
    "bun": 2,
    "bun run": 3,
    "bun x": 3,
    "cargo": 2,
    "cargo add": 3,
    "cargo run": 3,
    "cdk": 2,
    "cf": 2,
    "cmake": 2,
    "composer": 2,
    "consul": 2,
    "consul kv": 3,
    "crictl": 2,
    "deno": 2,
    "deno task": 3,
    "doctl": 3,
    "docker": 2,
    "docker builder": 3,
    "docker compose": 3,
    "docker container": 3,
    "docker image": 3,
    "docker network": 3,
    "docker volume": 3,
    "eksctl": 2,
    "eksctl create": 3,
    "firebase": 2,
    "flyctl": 2,
    "gcloud": 3,
    "gh": 3,
    "git": 2,
    "git config": 3,
    "git remote": 3,
    "git stash": 3,
    "go": 2,
    "gradle": 2,
    "helm": 2,
    "heroku": 2,
    "hugo": 2,
    "ip": 2,
    "ip addr": 3,
    "ip link": 3,
    "ip netns": 3,
    "ip route": 3,
    "kind": 2,
    "kind create": 3,
    "kubectl": 2,
    "kubectl kustomize": 3,
    "kubectl rollout": 3,
    "kustomize": 2,
    "make": 2,
    "mc": 2,
    "mc admin": 3,
    "minikube": 2,
    "mongosh": 2,
    "mysql": 2,
    "mvn": 2,
    "ng": 2,
    "npm": 2,
    "npm exec": 3,
    "npm init": 3,
    "npm run": 3,
    "npm view": 3,
    "nvm": 2,
    "nx": 2,
    "openssl": 2,
    "openssl req": 3,
    "openssl x509": 3,
    "pip": 2,
    "pipenv": 2,
    "pnpm": 2,
    "pnpm dlx": 3,
    "pnpm exec": 3,
    "pnpm run": 3,
    "poetry": 2,
    "podman": 2,
    "podman container": 3,
    "podman image": 3,
    "psql": 2,
    "pulumi": 2,
    "pulumi stack": 3,
    "pyenv": 2,
    "python": 2,
    "rake": 2,
    "rbenv": 2,
    "redis-cli": 2,
    "rustup": 2,
    "serverless": 2,
    "sfdx": 3,
    "skaffold": 2,
    "sls": 2,
    "sst": 2,
    "swift": 2,
    "systemctl": 2,
    "terraform": 2,
    "terraform workspace": 3,
    "tmux": 2,
    "turbo": 2,
    "ufw": 2,
    "vault": 2,
    "vault auth": 3,
    "vault kv": 3,
    "vercel": 2,
    "volta": 2,
    "wp": 2,
    "yarn": 2,
    "yarn dlx": 3,
    "yarn run": 3,
}


def command_prefix(tokens: list[str]) -> list[str]:
    """Determine the command prefix (human-understandable command) from a tokenized shell command.

    Uses the ARITY dictionary to find how many tokens define the command.
    Falls back to 1 token if no match found.
    """
    for length in range(len(tokens), 0, -1):
        prefix = " ".join(tokens[:length])
        arity = ARITY.get(prefix)
        if arity is not None:
            return tokens[:arity]
    if not tokens:
        return []
    return tokens[:1]


# ═══════════════════════════════════════════════════════════
# ForwardRef — 进程级跨 session 委托授权
# ═══════════════════════════════════════════════════════════

import sqlite3
import time

from typing import Callable


Decision = str  # "allow" | "deny"


@dataclass
class PendingRec:
    childSessionID: str
    parentSessionID: str
    resolve: Callable[[Decision], None]


# The parent's grant snapshot as two ordered phases (ruleset, approved)
# NEVER flattened, so a child mirrors the parent's two-phase evaluation.
@dataclass
class ParentGrantSnapshot:
    ruleset: list[Rule] = field(default_factory=list)
    approved: list[Rule] = field(default_factory=list)


PERMISSION_GRANT_DDL = """
CREATE TABLE IF NOT EXISTS permission_grant (
    parent_session_id TEXT NOT NULL,
    target TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (parent_session_id, target)
);
"""


class ForwardRef:
    """Process-global forward/grant ref for orchestrator child-session permission routing."""

    def __init__(self):
        self._grants: dict[str, set[str]] = {}
        self._pending: dict[str, PendingRec] = {}
        self._parent_grants: dict[str, ParentGrantSnapshot] = {}
        self._db_path: str | None = None

    def set_db_path(self, path: str):
        """Set the shared SQLite database path for grant persistence."""
        self._db_path = path
        conn = sqlite3.connect(path)
        conn.executescript(PERMISSION_GRANT_DDL)
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection | None:
        if self._db_path:
            return sqlite3.connect(self._db_path)
        return None

    def set_grant(self, parent_session_id: str, target: str):
        """Grant permission from parent to child (or '*' for all). Write-through to DB."""
        if parent_session_id not in self._grants:
            self._grants[parent_session_id] = set()
        self._grants[parent_session_id].add(target)

        # Write-through to shared SQLite
        conn = self._get_conn()
        if conn:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO permission_grant (parent_session_id, target, created_at) VALUES (?, ?, ?)",
                    (parent_session_id, target, time.time()),
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    def grant_allowed(self, parent_session_id: str, child_session_id: str) -> bool:
        """Check if a child has a grant from the parent."""
        # In-memory fast path
        s = self._grants.get(parent_session_id)
        if s and (child_session_id in s or "*" in s):
            return True

        # Cross-process path: consult DB
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.execute(
                    "SELECT target FROM permission_grant WHERE parent_session_id = ?",
                    (parent_session_id,),
                )
                for row in cursor:
                    if row[0] == child_session_id or row[0] == "*":
                        return True
            except Exception:
                pass
            finally:
                conn.close()
        return False

    def clear_grants_for_parent(self, parent_session_id: str):
        """Remove all grants for a given parent session."""
        self._grants.pop(parent_session_id, None)

        conn = self._get_conn()
        if conn:
            try:
                conn.execute(
                    "DELETE FROM permission_grant WHERE parent_session_id = ?",
                    (parent_session_id,),
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    def clear_grants_for_child(self, child_session_id: str):
        """Remove all grants for a given child session."""
        for s in self._grants.values():
            s.discard(child_session_id)

        for req_id in list(self._pending.keys()):
            if self._pending[req_id].childSessionID == child_session_id:
                del self._pending[req_id]

        conn = self._get_conn()
        if conn:
            try:
                conn.execute(
                    "DELETE FROM permission_grant WHERE target = ?",
                    (child_session_id,),
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    def set_parent_grants(self, parent_session_id: str, snapshot: ParentGrantSnapshot):
        """Publish/refresh the parent session's grant snapshot so background children can inherit."""
        self._parent_grants[parent_session_id] = ParentGrantSnapshot(
            ruleset=list(snapshot.ruleset),
            approved=list(snapshot.approved),
        )

    def get_parent_grants(self, parent_session_id: str) -> ParentGrantSnapshot | None:
        return self._parent_grants.get(parent_session_id)

    def clear_parent_grants(self, parent_session_id: str):
        self._parent_grants.pop(parent_session_id, None)

    def add_pending(self, request_id: str, rec: PendingRec):
        self._pending[request_id] = rec

    def remove_pending(self, request_id: str):
        self._pending.pop(request_id, None)

    def find_pending_by_child(self, child_session_id: str) -> tuple[str, PendingRec] | None:
        for req_id, rec in self._pending.items():
            if rec.childSessionID == child_session_id:
                return req_id, rec
        return None

    def resolve(self, child_session_id: str, decision: Decision) -> bool:
        """Resolve the child's current pending forwarded ask (allow/deny). Returns True if one was found."""
        found = self.find_pending_by_child(child_session_id)
        if not found:
            return False
        req_id, rec = found
        rec.resolve(decision)
        del self._pending[req_id]
        return True

    @property
    def grants(self) -> dict[str, set[str]]:
        return self._grants

    @property
    def pending(self) -> dict[str, PendingRec]:
        return self._pending

    @property
    def parent_grants(self) -> dict[str, ParentGrantSnapshot]:
        return self._parent_grants


# Module-level singleton
forward_ref = ForwardRef()
