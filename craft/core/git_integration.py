"""
Git 集成 — 移植自 packages/opencode/src/git/
Git 操作、diff、commit、branch 管理
"""

from __future__ import annotations

import subprocess
from typing import Any


class GitError(Exception):
    pass


class Git:
    def __init__(self, repo_path: str | None = None):
        self._path = repo_path
        self._env = {}

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git"] + list(args),
                capture_output=True, text=True, timeout=30,
                cwd=self._path,
                env={**self._env},
            )
        except subprocess.TimeoutExpired:
            raise GitError("Git 操作超时")
        except FileNotFoundError:
            raise GitError("Git 未安装")

    def init(self) -> bool:
        r = self._run("init")
        return r.returncode == 0

    def clone(self, url: str, dest: str) -> bool:
        r = self._run("clone", url, dest)
        return r.returncode == 0

    def add(self, *paths: str) -> bool:
        if not paths:
            r = self._run("add", "-A")
        else:
            r = self._run("add", *paths)
        return r.returncode == 0

    def commit(self, message: str) -> dict:
        r = self._run("commit", "-m", message)
        return {"success": r.returncode == 0, "output": r.stdout or r.stderr}

    def diff(self, staged: bool = False, stat: bool = True) -> str:
        args = ["diff"]
        if staged:
            args.append("--cached")
        if stat:
            args.append("--stat")
        r = self._run(*args)
        return r.stdout or "(无变更)"

    def diff_detail(self) -> str:
        r = self._run("diff", "--no-color")
        return r.stdout[:3000]

    def log(self, count: int = 10) -> list[dict]:
        r = self._run("log", f"-{count}", "--format=%H|%ai|%s")
        commits = []
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 2)
            commits.append({"hash": parts[0], "date": parts[1], "message": parts[2] if len(parts) > 2 else ""})
        return commits

    def status(self) -> str:
        r = self._run("status", "--short")
        return r.stdout

    def branch(self) -> str:
        r = self._run("branch", "--show-current")
        return r.stdout.strip()

    def branches(self) -> list[str]:
        r = self._run("branch", "--format=%(refname:short)")
        return [b.strip() for b in r.stdout.strip().split("\n") if b.strip()]

    def checkout(self, branch: str) -> bool:
        r = self._run("checkout", branch)
        return r.returncode == 0

    def is_repo(self) -> bool:
        try:
            r = self._run("rev-parse", "--git-dir")
            return r.returncode == 0
        except GitError:
            return False

    def current_repo(self) -> str | None:
        try:
            r = self._run("config", "--get", "remote.origin.url")
            return r.stdout.strip() if r.returncode == 0 else None
        except GitError:
            return None


git = Git()
