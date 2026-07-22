"""
Git Worktree — 移植自 packages/opencode/src/worktree/
Git worktree 管理：创建、移除、重置
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any


# ── 事件定义 ────────────────────────────────────────────────

WORKTREE_EVENTS: dict[str, dict] = {}


def _define_worktree_event(name: str, props: dict) -> dict:
    """定义 worktree 事件类型"""
    evt = {"type": name, "properties": props}
    WORKTREE_EVENTS[name] = evt
    return evt


WORKTREE_READY = _define_worktree_event("worktree.ready", {
    "name": str,
    "branch": str,
})

WORKTREE_FAILED = _define_worktree_event("worktree.failed", {
    "message": str,
})


# ── 错误类型 ────────────────────────────────────────────────

class WorktreeError(Exception):
    pass


class NotGitError(WorktreeError):
    """项目不是 Git 仓库"""
    pass


class NameGenerationFailedError(WorktreeError):
    """无法生成唯一的工作树名"""
    pass


class CreateFailedError(WorktreeError):
    """创建失败"""
    pass


class RemoveFailedError(WorktreeError):
    """移除失败"""
    pass


class ResetFailedError(WorktreeError):
    """重置失败"""
    pass


class StartCommandFailedError(WorktreeError):
    """启动命令失败"""
    pass


# ── 数据结构 ────────────────────────────────────────────────

@dataclass
class WorktreeInfo:
    """工作树信息"""
    name: str
    branch: str
    directory: str


# ── 辅助函数 ────────────────────────────────────────────────

def _slugify(input_str: str) -> str:
    """字符串 slug 化"""
    return re.sub(r"[^a-z0-9]+", "-", input_str.strip().lower()).strip("-")


def _run_git(args: list[str], cwd: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """运行 Git 命令"""
    try:
        return subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _parse_worktree_list(text: str) -> list[dict[str, str | None]]:
    """解析 `git worktree list --porcelain` 输出"""
    entries: list[dict[str, str | None]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("worktree "):
            entries.append({"path": line[len("worktree "):].strip(), "branch": None})
        elif line.startswith("branch ") and entries:
            entries[-1]["branch"] = line[len("branch "):].strip()
    return entries


def _failed_removes_from_stderr(stderr: str) -> list[str]:
    """从 stderr 中提取 'failed to remove' 的文件列表"""
    result: list[str] = []
    for line in stderr.splitlines():
        match = re.match(r"^warning:\s+failed to remove\s+(.+?):\s+", line, re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip("'\"")
            if value:
                result.append(value)
    return result


# ── GitWorktree ──────────────────────────────────────────────

class GitWorktree:
    """Git Worktree 管理器 — 对应 TS Worktree.Service

    支持:
    - makeWorktreeInfo: 生成工作树信息
    - create: 创建并启动工作树
    - remove: 移除工作树
    - reset: 重置工作树
    - head: 获取 HEAD 引用
    - isPristine: 检查工作树是否干净
    """

    def __init__(self, repo_path: str | None = None):
        self._path = repo_path or os.getcwd()
        self._max_name_attempts = 26

    def _canonical(self, path: str) -> str:
        """规范化路径"""
        abs_path = os.path.abspath(path)
        real_path = os.path.realpath(abs_path) if os.path.exists(abs_path) else abs_path
        normalized = os.path.normpath(real_path)
        return normalized.lower() if os.name == "nt" else normalized

    def list(self) -> list[dict]:
        """列出所有工作树"""
        r = _run_git(["worktree", "list", "--porcelain"], cwd=self._path)
        if r.returncode != 0:
            return []
        entries = _parse_worktree_list(r.stdout)
        result = []
        for entry in entries:
            if entry.get("path"):
                branch = entry.get("branch", "")
                if branch:
                    branch = branch.replace("refs/heads/", "")
                result.append({"path": entry["path"], "branch": branch or ""})
        return result

    def add(self, branch: str, path: str | None = None) -> bool:
        """添加工作树

        Args:
            branch: 分支名
            path: 工作树路径（可选）
        """
        args = ["worktree", "add", "-b", branch]
        if path:
            args.append(path)
        else:
            args.extend([f"../{branch}"])
        r = _run_git(args, cwd=self._path)
        return r.returncode == 0

    def remove(self, directory: str) -> bool:
        """移除工作树（带清理）"""
        canonical_dir = self._canonical(directory)

        # 读取工作树列表
        list_r = _run_git(["worktree", "list", "--porcelain"], cwd=self._path)
        if list_r.returncode != 0:
            raise RemoveFailedError("Failed to read git worktrees")

        entries = _parse_worktree_list(list_r.stdout)

        # 尝试定位工作树
        entry = None
        for e in entries:
            if e.get("path") and self._canonical(e["path"]) == canonical_dir:
                entry = e
                break

        if not entry:
            # 目录可能残留
            if os.path.exists(canonical_dir):
                _run_git(["fsmonitor--daemon", "stop"], cwd=canonical_dir)
                import shutil
                shutil.rmtree(canonical_dir, ignore_errors=True)
            return True

        # 停止 fsmonitor
        _run_git(["fsmonitor--daemon", "stop"], cwd=entry["path"])

        # git worktree remove
        remove_r = _run_git(["worktree", "remove", "--force", entry["path"]], cwd=self._path)
        if remove_r.returncode != 0:
            # 检查是否已被移除
            next_r = _run_git(["worktree", "list", "--porcelain"], cwd=self._path)
            if next_r.returncode == 0:
                stale = None
                for e in _parse_worktree_list(next_r.stdout):
                    if e.get("path") and self._canonical(e["path"]) == canonical_dir:
                        stale = e
                        break
                if stale:
                    raise RemoveFailedError(remove_r.stderr or "Failed to remove git worktree")

        # 清理目录
        if os.path.exists(entry["path"]):
            import shutil
            shutil.rmtree(entry["path"], ignore_errors=True)

        # 删除分支
        if entry.get("branch"):
            branch = entry["branch"].replace("refs/heads/", "")
            _run_git(["branch", "-D", branch], cwd=self._path)

        return True

    def make_worktree_info(self, name: str | None = None, vcs: str = "git",
                           project_id: str = "", data_dir: str = "") -> WorktreeInfo:
        """生成工作树信息 (类似 TS makeWorktreeInfo)"""
        if vcs != "git":
            raise NotGitError("Worktrees are only supported for git projects")

        worktree_root = os.path.join(data_dir or ".", "worktree", project_id)
        os.makedirs(worktree_root, exist_ok=True)

        base = _slugify(name) if name else ""

        for attempt in range(self._max_name_attempts):
            wt_name = base if attempt == 0 and base else (
                base + "-" + str(int(time.time())) if base else str(int(time.time()))
            )
            branch = f"craft/{wt_name}"
            directory = os.path.join(worktree_root, wt_name)

            if os.path.exists(directory):
                continue

            # 检查分支是否已存在
            check = _run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=self._path)
            if check.returncode == 0:
                continue

            return WorktreeInfo(name=wt_name, branch=branch, directory=directory)

        raise NameGenerationFailedError("Failed to generate a unique worktree name")

    def head(self, directory: str) -> str:
        """获取工作树的 HEAD 引用"""
        r = _run_git(["symbolic-ref", "--quiet", "HEAD"], cwd=directory)
        if r.returncode != 0:
            raise WorktreeError("Failed to get HEAD")
        return r.stdout.strip()

    def is_pristine(self, directory: str, base: str) -> bool:
        """检查工作树是否干净"""
        # 检查是否有未提交变更
        r = _run_git(["diff", "--quiet", base], cwd=directory)
        return r.returncode == 0


git_worktree = GitWorktree()
