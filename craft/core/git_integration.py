"""
Git 集成 — 移植自 packages/opencode/src/git/
Git 操作、diff、commit、branch、merge-base、status
"""

from __future__ import annotations

import subprocess
from typing import Any


# ── Git 配置 ────────────────────────────────────────────────

GIT_CFG = [
    "--no-optional-locks",
    "-c", "core.autocrlf=false",
    "-c", "core.fsmonitor=false",
    "-c", "core.longpaths=true",
    "-c", "core.symlinks=true",
    "-c", "core.quotepath=false",
]


class GitError(Exception):
    pass


Kind = str  # "added" | "deleted" | "modified"


class GitResult:
    """Git 命令结果 — 对应 TS Git.Result"""

    def __init__(self, exit_code: int, text: str, stderr: str = ""):
        self.exit_code = exit_code
        self._text = text
        self._stderr = stderr

    def text(self) -> str:
        return self._text.strip()

    @property
    def stdout(self) -> str:
        return self._text

    @property
    def stderr(self) -> str:
        return self._stderr


class GitItem:
    """Git diff/status 条目"""
    def __init__(self, file: str, code: str, status: Kind):
        self.file = file
        self.code = code
        self.status = status


class GitStat:
    """Git stat 条目"""
    def __init__(self, file: str, additions: int, deletions: int):
        self.file = file
        self.additions = additions
        self.deletions = deletions


class GitBase:
    """Git 分支基础信息"""
    def __init__(self, name: str, ref: str):
        self.name = name
        self.ref = ref


def _kind(code: str) -> Kind:
    """从 Git 状态码推断变更类型"""
    if code == "??":
        return "added"
    if "U" in code:
        return "modified"
    if "A" in code and "D" not in code:
        return "added"
    if "D" in code and "A" not in code:
        return "deleted"
    return "modified"


def _nuls(text: str) -> list[str]:
    """按 NUL 分割"""
    return [s for s in text.split("\0") if s]


class Git:
    """Git 操作器 — 对应 TS Git.Service

    提供完整的 Git 操作接口:
    - run: 底层命令执行
    - branch: 当前分支名
    - prefix: Git 前缀
    - defaultBranch: 默认分支
    - hasHead: 是否有 HEAD
    - mergeBase: 两个分支的共同祖先
    - show: 显示文件内容
    - status: 文件状态
    - diff: 文件差异列表
    - stats: 文件统计
    """

    def __init__(self, repo_path: str | None = None):
        self._path = repo_path
        self._env: dict[str, str] = {}

    def run(self, args: list[str], cwd: str | None = None,
            env: dict[str, str] | None = None) -> GitResult:
        """运行 Git 命令 — 对应 TS Git.run"""
        try:
            r = subprocess.run(
                ["git"] + list(GIT_CFG) + list(args),
                capture_output=True, text=True, timeout=60,
                cwd=cwd or self._path,
                env={**(self._env), **(env or {})},
            )
            return GitResult(r.returncode, r.stdout, r.stderr)
        except subprocess.TimeoutExpired:
            raise GitError("Git 操作超时")
        except FileNotFoundError:
            raise GitError("Git 未安装")
        except Exception as e:
            return GitResult(1, "", str(e))

    def _text(self, args: list[str], cwd: str | None = None) -> str:
        """运行并返回文本"""
        return self.run(args, cwd=cwd).text()

    def _lines(self, args: list[str], cwd: str | None = None) -> list[str]:
        """运行并返回行列表"""
        text = self._text(args, cwd=cwd)
        return [l.strip() for l in text.splitlines() if l.strip()]

    def branch(self, cwd: str | None = None) -> str | None:
        """获取当前分支名 — 对应 TS Git.branch"""
        r = self.run(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=cwd or self._path)
        if r.exit_code != 0:
            return None
        text = r.text()
        return text or None

    def prefix(self, cwd: str | None = None) -> str:
        """获取 Git 前缀 — 对应 TS Git.prefix"""
        r = self.run(["rev-parse", "--show-prefix"], cwd=cwd or self._path)
        if r.exit_code != 0:
            return ""
        return r.text()

    def _primary_remote(self, cwd: str) -> str | None:
        """获取主要远程名"""
        remotes = self._lines(["remote"], cwd=cwd)
        if "origin" in remotes:
            return "origin"
        if len(remotes) == 1:
            return remotes[0]
        if "upstream" in remotes:
            return "upstream"
        return remotes[0] if remotes else None

    def default_branch(self, cwd: str | None = None) -> GitBase | None:
        """获取默认分支 — 对应 TS Git.defaultBranch"""
        cwd = cwd or self._path
        remote = self._primary_remote(cwd)

        if remote:
            head = self.run(["symbolic-ref", f"refs/remotes/{remote}/HEAD"], cwd=cwd)
            if head.exit_code == 0:
                ref = head.text().replace("refs/remotes/", "")
                name = ref[len(remote) + 1:] if ref.startswith(f"{remote}/") else ""
                if name:
                    return GitBase(name, ref)

        refs = self._lines(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=cwd)
        if "main" in refs:
            return GitBase("main", "main")
        if "master" in refs:
            return GitBase("master", "master")
        return None

    def has_head(self, cwd: str | None = None) -> bool:
        """检查是否有 HEAD — 对应 TS Git.hasHead"""
        r = self.run(["rev-parse", "--verify", "HEAD"], cwd=cwd or self._path)
        return r.exit_code == 0

    def merge_base(self, base: str, head: str = "HEAD", cwd: str | None = None) -> str | None:
        """获取合并祖先 — 对应 TS Git.mergeBase"""
        r = self.run(["merge-base", base, head], cwd=cwd or self._path)
        if r.exit_code != 0:
            return None
        text = r.text()
        return text or None

    def show(self, ref: str, file: str, prefix: str = "", cwd: str | None = None) -> str:
        """显示文件内容 — 对应 TS Git.show"""
        target = f"{prefix}{file}" if prefix else file
        r = self.run(["show", f"{ref}:{target}"], cwd=cwd or self._path)
        if r.exit_code != 0:
            return ""
        return r.text()

    def init(self) -> bool:
        r = self.run(["init"])
        return r.exit_code == 0

    def clone(self, url: str, dest: str) -> bool:
        r = self.run(["clone", url, dest])
        return r.exit_code == 0

    def add(self, *paths: str) -> bool:
        args = ["add", "-A"] if not paths else ["add", *paths]
        r = self.run(args)
        return r.exit_code == 0

    def commit(self, message: str) -> dict:
        r = self.run(["commit", "-m", message])
        return {"success": r.exit_code == 0, "output": r.stdout or r.stderr}

    def status(self, cwd: str | None = None) -> list[GitItem]:
        """获取文件状态 — 对应 TS Git.status

        返回变更文件列表，每项含 file/code/status。
        """
        cwd = cwd or self._path
        items = _nuls(
            self._text([
                "status", "--porcelain=v1", "--untracked-files=all",
                "--no-renames", "-z", "--", ".",
            ], cwd=cwd)
        )
        result: list[GitItem] = []
        for item in items:
            file_part = item[3:]
            if not file_part:
                continue
            code = item[:2]
            result.append(GitItem(file_part, code, _kind(code)))
        return result

    def diff(self, ref: str, cwd: str | None = None) -> list[GitItem]:
        """获取与某 ref 的差异 — 对应 TS Git.diff

        返回变更文件列表，通过 --name-status -z 解析。
        """
        cwd = cwd or self._path
        items = _nuls(
            self._text([
                "diff", "--no-ext-diff", "--no-renames",
                "--name-status", "-z", ref, "--", ".",
            ], cwd=cwd)
        )
        result: list[GitItem] = []
        i = 0
        while i < len(items):
            code = items[i]
            i += 1
            if i >= len(items):
                break
            file = items[i]
            i += 1
            if code and file:
                result.append(GitItem(file, code, _kind(code)))
        return result

    def stats(self, ref: str, cwd: str | None = None) -> list[GitStat]:
        """获取差异统计 — 对应 TS Git.stats

        通过 --numstat -z 获取每个文件的增删行数。
        """
        cwd = cwd or self._path
        items = _nuls(
            self._text([
                "diff", "--no-ext-diff", "--no-renames",
                "--numstat", "-z", ref, "--", ".",
            ], cwd=cwd)
        )
        result: list[GitStat] = []
        for item in items:
            a = item.find("\t")
            b = item.find("\t", a + 1)
            if a == -1 or b == -1:
                continue
            file_part = item[b + 1:]
            if not file_part:
                continue
            adds_str = item[:a]
            dels_str = item[a + 1:b]
            adds = 0 if adds_str == "-" else int(adds_str or "0")
            dels = 0 if dels_str == "-" else int(dels_str or "0")
            result.append(GitStat(file_part, adds if adds >= 0 else 0, dels if dels >= 0 else 0))
        return result

    def diff_text(self, staged: bool = False, stat: bool = True) -> str:
        """获取文本差异"""
        args = ["diff"]
        if staged:
            args.append("--cached")
        if stat:
            args.append("--stat")
        r = self.run(args)
        return r.stdout or "(无变更)"

    def diff_detail(self) -> str:
        r = self.run(["diff", "--no-color"])
        return r.stdout[:3000]

    def log(self, count: int = 10) -> list[dict]:
        r = self.run(["log", f"-{count}", "--format=%H|%ai|%s"])
        commits = []
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 2)
            commits.append({"hash": parts[0], "date": parts[1], "message": parts[2] if len(parts) > 2 else ""})
        return commits

    def branches(self) -> list[str]:
        r = self.run(["branch", "--format=%(refname:short)"])
        return [b.strip() for b in r.stdout.strip().split("\n") if b.strip()]

    def checkout(self, branch: str) -> bool:
        r = self.run(["checkout", branch])
        return r.exit_code == 0

    def is_repo(self) -> bool:
        try:
            r = self.run(["rev-parse", "--git-dir"])
            return r.exit_code == 0
        except GitError:
            return False

    def current_repo(self) -> str | None:
        try:
            r = self.run(["config", "--get", "remote.origin.url"])
            return r.stdout.strip() if r.exit_code == 0 else None
        except GitError:
            return None


git = Git()
