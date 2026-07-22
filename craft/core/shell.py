"""
Shell 集成 — 移植自 packages/opencode/src/shell/
Shell 命令、自动补全、执行环境
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any


class Shell:
    @staticmethod
    def quote(text: str) -> str:
        return shlex.quote(text)

    @staticmethod
    def split(text: str) -> list[str]:
        return shlex.split(text)

    @staticmethod
    def run(cmd: str, cwd: str | None = None, timeout: float = 30) -> dict:
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=cwd,
            )
            return {"output": r.stdout[-2000:], "error": r.stderr[-500:],
                    "return_code": r.returncode}
        except subprocess.TimeoutExpired:
            return {"output": "", "error": f"超时 ({timeout}s)", "return_code": -1}
        except Exception as e:
            return {"output": "", "error": str(e), "return_code": -1}

    @staticmethod
    def get_env() -> dict:
        return dict(os.environ)

    @staticmethod
    def expand_vars(text: str) -> str:
        return os.path.expandvars(text)


shell = Shell()
