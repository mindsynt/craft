"""
安装管理 — 移植自 packages/opencode/src/installation/
版本检测、更新、安装方法识别
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from craft import __version__
from craft.config import CONFIG_DIR


# ── 常量 ────────────────────────────────────────────────────

PACKAGE_NAME = "@mimo-ai/cli"  # 在 Python 中保留原名以供检测
INSTALLATION_VERSION = __version__
INSTALLATION_CHANNEL = os.environ.get("CRAFT_CHANNEL", "local")
INSTALLATION_LOCAL = INSTALLATION_CHANNEL == "local"
USER_AGENT = f"craft/{INSTALLATION_VERSION}/{INSTALLATION_CHANNEL}"


# ── 类型 ────────────────────────────────────────────────────

Method = str  # "curl" | "npm" | "pnpm" | "bun" | "brew" | "scoop" | "choco" | "unknown"
ReleaseType = str  # "patch" | "minor" | "major"


# ── 辅助函数 ────────────────────────────────────────────────

def _run(cmd: list[str], cwd: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """运行命令并返回结果"""
    try:
        return subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=30, cwd=cwd,
            env={**os.environ, **(env or {})},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return subprocess.CompletedProcess(cmd, 1, "", "")


def _text(cmd: list[str], **kw) -> str:
    """运行命令返回 stdout"""
    r = _run(cmd, **kw)
    return r.stdout.strip()


def get_release_type(current: str, latest: str) -> ReleaseType:
    """计算版本差异类型"""
    def parse(v: str) -> tuple[int, int]:
        parts = v.split(".")
        return (int(parts[0]) if len(parts) > 0 else 0,
                int(parts[1]) if len(parts) > 1 else 0)

    curr_major, curr_minor = parse(current)
    new_major, new_minor = parse(latest)
    if new_major > curr_major:
        return "major"
    if new_minor > curr_minor:
        return "minor"
    return "patch"


def is_preview() -> bool:
    """是否预览通道"""
    return INSTALLATION_CHANNEL != "latest"


def is_local() -> bool:
    """是否本地开发版本"""
    return INSTALLATION_CHANNEL == "local"


# ── 安装方法检测 ───────────────────────────────────────────

def detect_method() -> Method:
    """检测当前安装方法"""
    exec_path = sys.executable.lower()

    # curl 安装的检测
    if ".craft" in exec_path or ".local" in exec_path:
        return "curl"

    # 包管理器检测
    checks: list[tuple[Method, str, list[str]]] = [
        ("npm", PACKAGE_NAME, ["npm", "list", "-g", "--depth=0"]),
        ("pnpm", PACKAGE_NAME, ["pnpm", "list", "-g", "--depth=0"]),
        ("bun", PACKAGE_NAME, ["bun", "pm", "ls", "-g"]),
    ]

    # 按 exec_path 匹配排序
    def sort_key(check: tuple) -> int:
        name = check[0]
        return -1 if name in exec_path else (1 if exec_path in name else 0)

    checks.sort(key=sort_key)

    for method, package, cmd in checks:
        output = _text(cmd)
        if package in output:
            return method

    return "unknown"


# ── 最新版本查询 ────────────────────────────────────────────

def check_latest(method: Method | None = None) -> str:
    """检查最新版本"""
    detected = method or detect_method()

    if detected == "npm" or detected == "bun" or detected == "pnpm":
        # 通过 npm registry 查询
        r = _run(["npm", "config", "get", "registry"])
        reg = (r.stdout.strip() or "https://registry.npmjs.org").rstrip("/")
        import urllib.request
        import json
        url = f"{reg}/{PACKAGE_NAME}/{INSTALLATION_CHANNEL}"
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read())
            return data.get("version", "0.0.0")
        except Exception:
            return "0.0.0"

    # Fallback: 尝试从 FDS 或 GitHub 查询
    try:
        import urllib.request
        base = (os.environ.get("MIMO_FDS_BASE") or "https://mimocode.cnbj1.mi-fds.com/mimocode/mimocode").rstrip("/")
        resp = urllib.request.urlopen(f"{base}/releases/latest", timeout=10)
        version = resp.read().decode().strip().lstrip("v")
        if re.match(r"^\d+\.\d+\.\d+", version):
            return version
    except Exception:
        pass

    return "0.0.0"


def check_update() -> dict | None:
    """检查更新 — 返回 {version, latest} 或 None"""
    try:
        latest = check_latest()
        if latest and latest != INSTALLATION_VERSION:
            return {"version": INSTALLATION_VERSION, "latest": latest}
    except Exception:
        pass
    return None


# ── 更新执行 ────────────────────────────────────────────────

class UpgradeError(Exception):
    def __init__(self, stderr: str = ""):
        self.stderr = stderr
        super().__init__(stderr)


def upgrade(method: Method, target: str):
    """执行升级"""
    if method == "npm":
        r = _run(["npm", "install", "-g", f"{PACKAGE_NAME}@{target}"])
    elif method == "pnpm":
        r = _run(["pnpm", "install", "-g", f"{PACKAGE_NAME}@{target}"])
    elif method == "bun":
        r = _run(["bun", "install", "-g", f"{PACKAGE_NAME}@{target}"])
    else:
        raise UpgradeError(f"Unknown method: {method}")

    if r.returncode != 0:
        raise UpgradeError(r.stderr or r.stdout)


# ── Installation 类 ─────────────────────────────────────────

class Installation:
    """安装信息管理器"""

    def __init__(self):
        self.version = INSTALLATION_VERSION
        self.install_dir = Path(__file__).parent.parent
        self.config_dir = CONFIG_DIR

    @property
    def channel(self) -> str:
        return INSTALLATION_CHANNEL

    @property
    def is_latest(self) -> bool:
        return True  # 简化版

    @property
    def build_info(self) -> dict:
        return {
            "version": self.version,
            "channel": self.channel,
            "python": os.sys.version,
        }

    @property
    def method(self) -> Method:
        return detect_method()

    def info(self) -> dict:
        return {
            "version": self.version,
            "latest": check_latest(),
        }


installation = Installation()
