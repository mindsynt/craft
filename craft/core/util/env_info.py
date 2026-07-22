"""环境信息 — 移植自 env-info.ts

收集当前运行环境的系统、CPU、内存、用户和运行时信息。
"""

from __future__ import annotations

import os
import platform
import sys


def get_env_info() -> dict:
    """获取当前环境信息

    对应 TS getEnvInfo()。返回系统、CPU、内存、用户、运行时和项目自身信息。
    """
    uname = platform.uname()

    info = {
        "os": {
            "platform": sys.platform,
            "arch": platform.machine(),
            "release": platform.release(),
            "hostname": uname.node,
        },
        "cpu": {
            "model": _cpu_model(),
            "count": os.cpu_count() or 1,
        },
        "memory": {
            "total_bytes": _total_memory(),
        },
        "user": {
            "username": _username(),
            "homedir": os.path.expanduser("~"),
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "pid": os.getpid(),
            "timezone": _timezone(),
            "locale": _locale(),
        },
        "paths": {
            "cwd": os.getcwd(),
        },
        "craft": {
            "version": _get_craft_version(),
            "channel": os.environ.get("CRAFT_CHANNEL", "local"),
        },
    }
    return info


def _username() -> str:
    """获取当前用户名"""
    return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def _timezone() -> str:
    """获取时区"""
    try:
        import datetime
        return datetime.datetime.now().astimezone().tzname() or "UTC"
    except Exception:
        return "UTC"


def _locale() -> str:
    """获取系统 locale"""
    import locale as _locale_mod
    try:
        return _locale_mod.getdefaultlocale()[0] or "C"
    except Exception:
        return "C"


def _cpu_model() -> str:
    """获取 CPU 型号"""
    if sys.platform == "darwin":
        try:
            import subprocess
            r = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
    elif sys.platform == "linux":
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":")[1].strip()
        except Exception:
            pass
    return platform.processor() or "unknown"


def _total_memory() -> int:
    """获取总内存字节数"""
    if sys.platform == "darwin":
        try:
            import subprocess
            r = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return int(r.stdout.strip())
        except Exception:
            pass
    elif sys.platform == "linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb * 1024
        except Exception:
            pass
    return 0


def _get_craft_version() -> str:
    """获取 Craft 版本"""
    try:
        from craft import __version__
        return __version__
    except (ImportError, AttributeError):
        return "0.0.0"
