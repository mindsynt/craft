"""
特性开关系统 — 移植自 packages/opencode/src/flag/
支持条件表达式、环境变量覆盖、配置开关
"""

from __future__ import annotations

import os
from typing import Any


class Flag:
    def __init__(self, name: str, default: bool = False, description: str = ""):
        self.name = name
        self.default = default
        self.description = description
        self._overrides: dict[str, bool] = {}

    def is_enabled(self) -> bool:
        if self.name in self._overrides:
            return self._overrides[self.name]
        env = os.environ.get(f"CRAFT_FLAG_{self.name.upper()}")
        if env is not None:
            return env.lower() in ("1", "true", "yes")
        return self.default

    def enable(self):
        self._overrides[self.name] = True

    def disable(self):
        self._overrides[self.name] = False


class FlagManager:
    def __init__(self):
        self._flags: dict[str, Flag] = {}

    def define(self, name: str, default: bool = False, description: str = "") -> Flag:
        flag = Flag(name, default, description)
        self._flags[name] = flag
        return flag

    def get(self, name: str) -> bool:
        flag = self._flags.get(name)
        return flag.is_enabled() if flag else False

    def list(self) -> list[dict]:
        return [{"name": f.name, "enabled": f.is_enabled(), "description": f.description}
                for f in self._flags.values()]


flags = FlagManager()

# 内置特性开关
flags.define("plugin_system", default=True, description="启用插件系统")
flags.define("cron_scheduler", default=False, description="启用定时调度")
flags.define("slack_integration", default=False, description="启用 Slack 集成")
flags.define("inbox_notifications", default=True, description="启用通知收件箱")
flags.define("enterprise_mode", default=False, description="企业版模式")
flags.define("snapshot_tracking", default=True, description="文件快照跟踪")
flags.define("cc_memory_import", default=False, description="导入 Claude Code 记忆")
