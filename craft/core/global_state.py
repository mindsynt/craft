"""
全局状态 — 移植自 packages/opencode/src/global/
应用路径、环境信息、运行时上下文
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from craft.config import CONFIG_DIR


CACHE_VERSION = "21"


class GlobalPaths:
    """全局路径 — 移植自 TS Global.Path

    基于 {home}/.craft/ 目录结构：
    - data: 持久化数据
    - cache: 缓存（可清空）
    - config: 配置
    - state: 运行时状态
    - log: 日志
    - bin: 二进制文件
    """
    _home_cache: str | None = None

    @classmethod
    @property
    def home(cls) -> str:
        """HOME 目录（运行时可变，用于测试隔离）"""
        if cls._home_cache is not None:
            return cls._home_cache
        return os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.path.expanduser("~")

    @classmethod
    def set_home(cls, path: str):
        """设置 HOME 覆盖（用于测试）"""
        cls._home_cache = path

    @classmethod
    @property
    def data(cls) -> Path:
        return CONFIG_DIR / "data"

    @classmethod
    @property
    def cache(cls) -> Path:
        return CONFIG_DIR / "cache"

    @classmethod
    @property
    def config(cls) -> Path:
        return CONFIG_DIR / "config"

    @classmethod
    @property
    def state(cls) -> Path:
        return CONFIG_DIR / "state"

    @classmethod
    @property
    def log(cls) -> Path:
        return CONFIG_DIR / "log"

    @classmethod
    @property
    def bin(cls) -> Path:
        return cls.cache / "bin"

    @classmethod
    @property
    def plugins(cls) -> Path:
        return CONFIG_DIR / "plugins"

    @classmethod
    @property
    def memory(cls) -> Path:
        return CONFIG_DIR / "memory"

    @classmethod
    def ensure(cls):
        """确保所有目录存在"""
        for p in [cls.data, cls.cache, cls.config, cls.state, cls.log, cls.bin, cls.plugins, cls.memory]:
            p.mkdir(parents=True, exist_ok=True)

    @classmethod
    async def orchestrator_dir(cls) -> Path:
        """全局 Orchestrator 工作目录"""
        dir_path = cls.data / "orchestrator"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @classmethod
    def ensure_cache_version(cls):
        """缓存版本检查 — 版本不匹配则清空缓存

        对应 TS: const CACHE_VERSION = "21" + 版本清空逻辑
        """
        version_file = cls.cache / "version"
        try:
            current_version = version_file.read_text().strip()
        except FileNotFoundError:
            current_version = "0"

        if current_version != CACHE_VERSION:
            if cls.cache.exists():
                for item in cls.cache.iterdir():
                    if item.name != "version":
                        try:
                            if item.is_dir():
                                shutil.rmtree(item)
                            else:
                                item.unlink()
                        except Exception:
                            pass
            cls.cache.mkdir(parents=True, exist_ok=True)
            version_file.write_text(CACHE_VERSION)


class GlobalState:
    """全局运行时状态（单例）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.start_time = None
            cls._instance.work_dir = Path.cwd()
        return cls._instance

    @property
    def cwd(self) -> Path:
        return Path.cwd()

    @cwd.setter
    def cwd(self, path: str | Path):
        os.chdir(path)


global_state = GlobalState()
