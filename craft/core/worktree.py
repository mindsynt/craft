"""
Git Worktree — 移植自 packages/opencode/src/worktree/
Git worktree 管理
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


class GitWorktree:
    def __init__(self, repo_path: str | None = None):
        self._path = repo_path or os.getcwd()

    def list(self) -> list[dict]:
        try:
            r = subprocess.run(
                ["git", "worktree", "list"],
                capture_output=True, text=True, timeout=10,
                cwd=self._path,
            )
            trees = []
            for line in r.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    trees.append({"path": parts[0], "branch": parts[1].strip("[]")})
            return trees
        except Exception:
            return []

    def add(self, branch: str, path: str | None = None) -> bool:
        try:
            args = ["git", "worktree", "add"]
            if path:
                args.extend([path, branch])
            else:
                args.extend(["-b", branch, f"../{branch}"])
            r = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=self._path)
            return r.returncode == 0
        except Exception:
            return False

    def remove(self, path: str) -> bool:
        try:
            r = subprocess.run(
                ["git", "worktree", "remove", path],
                capture_output=True, text=True, timeout=10, cwd=self._path,
            )
            return r.returncode == 0
        except Exception:
            return False


git_worktree = GitWorktree()
