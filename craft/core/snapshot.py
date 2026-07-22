"""
文件快照系统 — 移植自 packages/opencode/src/snapshot/
使用 Git 跟踪文件变更：write-tree, diff, checkout 实现快照/恢复/撤销
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from craft.config import CONFIG_DIR

SNAPSHOT_DB = CONFIG_DIR / "snapshots.json"

# ── 快照配置 ────────────────────────────────────────────────

PRUNE_AGE = "7.days"
LIMIT_BYTES = 2 * 1024 * 1024  # 2MB 限制

GIT_CORE = ["-c", "core.longpaths=true", "-c", "core.symlinks=true"]
GIT_CFG = ["-c", "core.autocrlf=false"] + GIT_CORE
GIT_QUOTE = GIT_CFG + ["-c", "core.quotepath=false"]


# ── 辅助 ────────────────────────────────────────────────────

def _run_git(args: list[str], cwd: str | None = None, env: dict | None = None,
             timeout: int = 60, stdin: str | None = None) -> subprocess.CompletedProcess:
    """运行 git 命令"""
    try:
        return subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd, env={**os.environ, **(env or {})},
            input=stdin,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


# ── Snapshot ─────────────────────────────────────────────────

class SnapshotFile:
    """快照中的文件"""
    def __init__(self, path: str):
        self.path = path
        self.hash = ""


class Patch:
    """补丁 — 对应 TS Snapshot.Patch"""
    def __init__(self, hash: str, files: list[str]):
        self.hash = hash
        self.files = files


class FileDiff:
    """文件差异 — 对应 TS Snapshot.FileDiff"""
    def __init__(self, file: str, patch: str, additions: int, deletions: int,
                 status: str | None = None):
        self.file = file
        self.patch = patch
        self.additions = additions
        self.deletions = deletions
        self.status = status


class SnapshotManager:
    """快照管理器 — 基于 Git 的快照系统

    使用独立的 git 仓库（在 ~/.craft/snapshot/<project_id>/<worktree_hash>/ 下）
    来跟踪文件变更，支持：
    - track: 记录当前快照
    - patch: 获取两个快照间的文件变更
    - restore: 恢复到某个快照
    - revert: 撤销多个补丁
    - diff: 查看差异
    - cleanup: 清理过期数据
    """

    def __init__(self):
        self._snapshots: list[dict] = []
        self._max_per_file = 20
        self._load()

    def _load(self):
        try:
            if SNAPSHOT_DB.exists():
                self._snapshots = json.loads(SNAPSHOT_DB.read_text())
        except Exception:
            self._snapshots = []

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_DB.write_text(json.dumps(self._snapshots[-500:], indent=2, default=str))

    def _snapshot_git_dir(self, project_id: str, worktree: str) -> str:
        """获取快照 Git 仓库路径"""
        fast_hash = hashlib.md5(worktree.encode()).hexdigest()[:16]
        return str(CONFIG_DIR / "snapshot" / project_id / fast_hash)

    def _ensure_git_repo(self, gitdir: str, worktree: str):
        """确保快照 Git 仓库存在并初始化"""
        if not os.path.exists(gitdir):
            os.makedirs(gitdir, exist_ok=True)
            _run_git(["init"], env={"GIT_DIR": gitdir, "GIT_WORK_TREE": worktree})
            _run_git(["--git-dir", gitdir, "config", "core.autocrlf", "false"])
            _run_git(["--git-dir", gitdir, "config", "core.longpaths", "true"])
            _run_git(["--git-dir", gitdir, "config", "core.symlinks", "true"])
            _run_git(["--git-dir", gitdir, "config", "core.fsmonitor", "false"])

    def track(self, worktree: str, project_id: str = "default") -> str | None:
        """跟踪当前快照

        使用 git write-tree 生成树哈希。
        对应 TS Snapshot.track
        """
        gitdir = self._snapshot_git_dir(project_id, worktree)
        self._ensure_git_repo(gitdir, worktree)

        # Stage 当前文件
        args = GIT_CFG + ["--git-dir", gitdir, "--work-tree", worktree,
                          "add", "--all", "--sparse", "."]
        _run_git(args, cwd=worktree)

        # 生成树哈希
        result = _run_git(GIT_CFG + ["--git-dir", gitdir, "--work-tree", worktree, "write-tree"],
                          cwd=worktree)
        if result.returncode != 0:
            return None

        tree_hash = result.stdout.strip()

        # 记录快照
        snap = {
            "id": f"snap_{uuid.uuid4().hex[:12]}",
            "hash": tree_hash,
            "worktree": worktree,
            "project_id": project_id,
            "timestamp": time.time(),
        }
        self._snapshots.append(snap)
        self._save()
        return tree_hash

    def diff(self, hash: str, worktree: str, project_id: str = "default") -> str:
        """获取快照差异 — 对应 TS Snapshot.diff"""
        gitdir = self._snapshot_git_dir(project_id, worktree)
        if not os.path.exists(gitdir):
            return ""

        # Stage 当前变更
        args = GIT_CFG + ["--git-dir", gitdir, "--work-tree", worktree, "add", "--all", "--sparse", "."]
        _run_git(args, cwd=worktree)

        result = _run_git(
            GIT_QUOTE + ["--git-dir", gitdir, "--work-tree", worktree,
                         "diff", "--cached", "--no-ext-diff", hash, "--", "."],
            cwd=worktree,
        )
        return result.stdout

    def diff_full(self, from_hash: str, to_hash: str, worktree: str,
                  project_id: str = "default") -> list[FileDiff]:
        """获取完整差异 — 对应 TS Snapshot.diffFull"""
        gitdir = self._snapshot_git_dir(project_id, worktree)
        if not os.path.exists(gitdir):
            return []

        # 获取变更文件列表
        result = _run_git(
            GIT_QUOTE + ["--git-dir", gitdir, "--work-tree", worktree,
                         "diff", "--cached", "--no-ext-diff",
                         "--name-only", from_hash, to_hash, "--", "."],
            cwd=worktree,
        )
        if result.returncode != 0:
            return []

        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]

        # 获取补丁
        patch_result = _run_git(
            GIT_CFG + ["--git-dir", gitdir, "--work-tree", worktree,
                       "diff", "--cached", "--no-ext-diff",
                       from_hash, to_hash, "--", "."],
            cwd=worktree,
        )

        diffs: list[FileDiff] = []
        for file in files:
            diffs.append(FileDiff(
                file=file,
                patch=patch_result.stdout,
                additions=0,
                deletions=0,
            ))
        return diffs

    def restore(self, snapshot_hash: str, worktree: str, project_id: str = "default") -> bool:
        """恢复到指定快照 — 对应 TS Snapshot.restore

        使用 git read-tree + checkout-index 恢复文件。
        """
        gitdir = self._snapshot_git_dir(project_id, worktree)
        if not os.path.exists(gitdir):
            return False

        # read-tree
        result = _run_git(
            GIT_CORE + ["--git-dir", gitdir, "--work-tree", worktree, "read-tree", snapshot_hash],
            cwd=worktree,
        )
        if result.returncode != 0:
            return False

        # checkout-index
        result = _run_git(
            GIT_CORE + ["--git-dir", gitdir, "--work-tree", worktree, "checkout-index", "-a", "-f"],
            cwd=worktree,
        )
        return result.returncode == 0

    def revert(self, patches: list[Patch], worktree: str, project_id: str = "default") -> bool:
        """撤销多个补丁 — 对应 TS Snapshot.revert

        从每个补丁的 hash 检出对应文件。
        """
        gitdir = self._snapshot_git_dir(project_id, worktree)
        if not os.path.exists(gitdir):
            return False

        seen: set[str] = set()
        ops: list[tuple[str, str, str]] = []  # (hash, file, rel_path)

        for patch_item in patches:
            for file in patch_item.files:
                if file in seen:
                    continue
                seen.add(file)
                rel = os.path.relpath(file, worktree).replace("\\", "/")
                ops.append((patch_item.hash, file, rel))

        for hash_val, file_path, rel in ops:
            result = _run_git(
                GIT_CORE + ["--git-dir", gitdir, "--work-tree", worktree,
                            "checkout", hash_val, "--", file_path],
                cwd=worktree,
            )
            if result.returncode != 0:
                # 文件可能在快照中不存在，删除
                tree_result = _run_git(
                    GIT_CORE + ["--git-dir", gitdir, "--work-tree", worktree,
                                "ls-tree", hash_val, "--", rel],
                    cwd=worktree,
                )
                if tree_result.returncode != 0 or not tree_result.stdout.strip():
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass

        return True

    def cleanup(self, worktree: str, project_id: str = "default") -> bool:
        """清理快照仓库 — 对应 TS Snapshot.cleanup"""
        gitdir = self._snapshot_git_dir(project_id, worktree)
        if not os.path.exists(gitdir):
            return True

        result = _run_git(
            ["--git-dir", gitdir, "--work-tree", worktree, "gc", f"--prune={PRUNE_AGE}"],
            cwd=worktree,
        )
        return result.returncode == 0

    # ── 原有快照功能 ──────────────────────────────────────

    def capture(self, filepath: str, operation: str = "edit") -> dict | None:
        """捕获文件快照"""
        if not os.path.isfile(filepath):
            return None
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except Exception:
            return None
        snap = {
            "id": f"snap_{uuid.uuid4().hex[:12]}",
            "filepath": filepath,
            "content": content,
            "hash": hashlib.md5(content.encode()).hexdigest(),
            "operation": operation,
            "timestamp": time.time(),
        }
        self._snapshots.append(snap)

        # 限制每个文件最大快照数
        file_snaps = [s for s in self._snapshots if s.get("filepath") == filepath]
        while len(file_snaps) > self._max_per_file:
            oldest = file_snaps.pop(0)
            self._snapshots.remove(oldest)

        self._save()
        return snap

    def restore_file(self, snap_id: str) -> bool:
        """恢复到指定快照"""
        for s in self._snapshots:
            if s.get("id") == snap_id and "filepath" in s:
                try:
                    Path(s["filepath"]).write_text(s.get("content", ""), encoding="utf-8")
                    return True
                except Exception:
                    return False
        return False

    def list(self, filepath: str | None = None, limit: int = 50) -> list[dict]:
        snaps = self._snapshots
        if filepath:
            snaps = [s for s in snaps if s.get("filepath") == filepath]
        return snaps[-limit:]

    def clear(self, filepath: str | None = None):
        if filepath:
            self._snapshots = [s for s in self._snapshots if s.get("filepath") != filepath]
        else:
            self._snapshots.clear()
        self._save()


snapshots = SnapshotManager()
