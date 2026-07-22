"""路径与目录操作 — 对应 paths.ts, gitignore.ts"""

from __future__ import annotations

import os
from pathlib import Path

from .error import ConfigJsonError

# ═══════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════

CONFIG_DIR = Path.home() / ".craft"
PROJECT_CONFIG_FILES = ["craft.jsonc", "craft.json", ".craft/config.jsonc", ".craft/config.json"]


# ═══════════════════════════════════════════════════════════
# Gitignore (对应 gitignore.ts)
# ═══════════════════════════════════════════════════════════

MIMOCODE_GITIGNORE_ENTRIES = [
    "node_modules",
    "package.json",
    "package-lock.json",
    "bun.lock",
    ".gitignore",
    ".cron-lock",
    "scheduled_tasks.json",
]


def ensure_gitignore(dir_path: str) -> None:
    """确保 .craft 目录有 .gitignore"""
    gitignore_path = Path(dir_path) / ".gitignore"
    if gitignore_path.exists():
        return
    try:
        gitignore_path.write_text("\n".join(MIMOCODE_GITIGNORE_ENTRIES))
    except PermissionError:
        pass


# ═══════════════════════════════════════════════════════════
# Paths (对应 paths.ts)
# ═══════════════════════════════════════════════════════════


def find_config_files(name: str, start_dir: str, stop_dir: str | None = None) -> list[str]:
    """从 start_dir 向上查找所有匹配的配置文件"""
    results: list[str] = []
    current = Path(start_dir).resolve()
    stop = Path(stop_dir).resolve() if stop_dir else None

    while True:
        for ext in [".jsonc", ".json"]:
            p = current / f"{name}{ext}"
            if p.exists():
                results.append(str(p))
        if stop and current == stop:
            break
        if current.parent == current:
            break
        current = current.parent

    results.reverse()
    return results


def find_config_directories(start_dir: str, stop_dir: str | None = None) -> list[str]:
    """从 start_dir 向上查找所有 .craft 目录"""
    dirs: list[str] = []
    cfg_dir_path = str(CONFIG_DIR)  # global dir always first

    current = Path(start_dir).resolve()
    stop = Path(stop_dir).resolve() if stop_dir else None

    while True:
        craft_dir = current / ".craft"
        if craft_dir.is_dir():
            dirs.append(str(craft_dir))
        if stop and current == stop:
            break
        if current.parent == current:
            break
        current = current.parent

    dirs = [cfg_dir_path] + dirs

    # deduplicate
    seen: set[str] = set()
    unique = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


def read_config_file(filepath: str) -> str | None:
    """读取配置文件，不存在返回 None"""
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except Exception as e:
        raise ConfigJsonError(filepath, str(e)) from e
