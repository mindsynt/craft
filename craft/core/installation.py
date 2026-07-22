"""
安装管理 — 移植自 packages/opencode/src/installation/
版本检测、更新、安装
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from craft import __version__
from craft.config import CONFIG_DIR


class Installation:
    def __init__(self):
        self.version = __version__
        self.install_dir = Path(__file__).parent.parent
        self.config_dir = CONFIG_DIR

    @property
    def is_latest(self) -> bool:
        return True

    @property
    def channel(self) -> str:
        return os.environ.get("CRAFT_CHANNEL", "stable")

    @property
    def build_info(self) -> dict:
        return {"version": self.version, "channel": self.channel, "python": os.sys.version}

    def check_update(self) -> dict | None:
        return None


installation = Installation()
