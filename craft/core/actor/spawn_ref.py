"""
Spawn 引用 — 移植自 packages/opencode/src/actor/spawn-ref.ts

解决 Actor 层循环依赖：SessionCheckpoint 需要生成 checkpoint-writer 子代理，
但通过 Actor 服务直接依赖会导致循环。使用模块级全局引用来打破循环。

渲染/只读路径从不调用 tryStartCheckpointWriter，所以 missing current 是
运行时守卫而非硬性不变式。
"""

from __future__ import annotations

import threading
from typing import Any


# 线程级 Actor 服务引用
_current: threading.local = threading.local()


class SpawnRef:
    """Actor 服务后期的、绑定的引用 — 移植自 spawn-ref.ts

    用法：
      在 Actor 初始化时：SpawnRef.set(actor_service_instance)
      在需要调用处：service = SpawnRef.get()
      清理时：SpawnRef.clear()
    """

    @staticmethod
    def get() -> Any | None:
        return getattr(_current, "value", None)

    @staticmethod
    def set(value: Any) -> None:
        _current.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current, "value"):
            del _current.value
