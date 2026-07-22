"""
运行时引用 — 移植自 packages/opencode/src/workflow/runtime-ref.ts
"""

from __future__ import annotations

import threading
from typing import Any


_current_workflow_runtime: threading.local = threading.local()


class WorkflowRuntimeRef:
    """工作流运行时引用 — 移植自 runtime-ref.ts"""

    @staticmethod
    def get() -> Any | None:
        return getattr(_current_workflow_runtime, "value", None)

    @staticmethod
    def set(value: Any) -> None:
        _current_workflow_runtime.value = value

    @staticmethod
    def clear() -> None:
        if hasattr(_current_workflow_runtime, "value"):
            del _current_workflow_runtime.value
