"""
NPM 集成 — 移植自 packages/opencode/src/npm/
包管理、依赖安装、版本检测
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class NPM:
    def __init__(self, cwd: str | None = None):
        self.cwd = cwd

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["npm"] + list(args), capture_output=True, text=True,
                timeout=60, cwd=self.cwd,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, -1, "", "超时")

    def install(self, packages: list[str] | None = None) -> bool:
        args = ["install"]
        if packages:
            args.extend(packages)
        r = self._run(*args)
        return r.returncode == 0

    def init_package_json(self, path: str) -> bool:
        p = Path(path)
        if not (p / "package.json").exists():
            pkg = {"name": p.name, "version": "0.1.0", "private": True}
            (p / "package.json").write_text(json.dumps(pkg, indent=2))
            return True
        return False

    def list_packages(self) -> list[dict]:
        r = self._run("list", "--depth=0", "--json")
        try:
            return json.loads(r.stdout).get("dependencies", {})
        except Exception:
            return []

    def search(self, query: str) -> list[dict]:
        r = self._run("search", query, "--json")
        try:
            return json.loads(r.stdout).get("results", [])
        except Exception:
            return []


npm = NPM()
