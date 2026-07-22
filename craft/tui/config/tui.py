"""
TUI 配置 — 移植自 config/tui.ts

TUI 配置加载：全局配置 → MIMOCODE_TUI_CONFIG → 项目配置 → .mimocode 配置。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

TUI_SCHEMA_URL = "https://craft.ai/tui.json"


class TuiConfigLoader:
    """TUI 配置加载器

    配置优先级（低→高）：
    1. 全局 tui.json
    2. $MIMOCODE_TUI_CONFIG 覆盖
    3. 项目 tui.json (根优先)
    4. .mimocode/tui.json
    """

    def __init__(self):
        self._cached: Optional[dict] = None

    async def load(self, directory: str, config_dir: Optional[str] = None) -> dict:
        """加载配置（支持 Effect 风格的调用）"""
        if self._cached is not None:
            return self._cached

        config: dict[str, Any] = {}

        # 1. Global config
        global_cfg = config_dir or os.path.expanduser("~/.craft")
        global_file = os.path.join(global_cfg, "tui.json")
        if os.path.isfile(global_file):
            try:
                with open(global_file) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        config = _deep_merge(config, data)
            except (json.JSONDecodeError, OSError):
                pass

        # 2. Environment override
        env_override = os.environ.get("CRAFT_TUI_CONFIG") or os.environ.get("MIMOCODE_TUI_CONFIG")
        if env_override and os.path.isfile(env_override):
            try:
                with open(env_override) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        config = _deep_merge(config, data)
            except (json.JSONDecodeError, OSError):
                pass

        # 3. Project config files (walk up from directory)
        project_files = _find_project_files(directory, "tui.json")
        for filepath in project_files:
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        config = _deep_merge(config, data)
            except (json.JSONDecodeError, OSError):
                pass

        # 4. .mimocode/tui.json
        mimocode_dir = os.path.join(directory, ".mimocode")
        mimocode_file = os.path.join(mimocode_dir, "tui.json")
        if os.path.isfile(mimocode_file):
            try:
                with open(mimocode_file) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        config = _deep_merge(config, data)
            except (json.JSONDecodeError, OSError):
                pass

        # Normalize keybinds
        keybinds = config.get("keybinds", {})
        if isinstance(keybinds, dict):
            # Platform-specific keybinds
            import platform as _platform
            if _platform.system().lower() == "windows":
                keybinds.pop("terminal_suspend", None)
                keybinds.setdefault("input_undo", "ctrl+z")
            config["keybinds"] = keybinds

        self._cached = config
        return config

    def invalidate(self):
        """清除缓存"""
        self._cached = None


def _deep_merge(base: dict, overlay: dict) -> dict:
    """深度合并两个字典"""
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _find_project_files(start_dir: str, filename: str) -> list[str]:
    """从 start_dir 向上查找项目配置文件"""
    files = []
    current = start_dir
    while True:
        candidate = os.path.join(current, filename)
        if os.path.isfile(candidate):
            files.append(candidate)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    # Return root-first
    files.reverse()
    return files
