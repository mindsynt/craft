"""运行服务 — attach, attach_with, make_runtime"""

from __future__ import annotations

from typing import Any, Callable

from .instance_state import InstanceRef, WorkspaceRef
from .memo_map import memo_map
from .runtime import Runtime


def attach_with(
    effect_fn: Callable[..., Any],
    refs: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """
    将 effect 与实例/工作区引用绑定
    对应 run-service.ts 的 attachWith
    """
    refs = refs or {}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        prev_instance = InstanceRef.get()
        prev_workspace = WorkspaceRef.get()
        try:
            if "instance" in refs:
                InstanceRef.set(refs["instance"])
            if "workspace" in refs:
                WorkspaceRef.set(refs["workspace"])
            return effect_fn(*args, **kwargs)
        finally:
            InstanceRef.set(prev_instance)
            WorkspaceRef.set(prev_workspace)

    return wrapper


def attach(effect_fn: Callable[..., Any]) -> Callable[..., Any]:
    """
    自动附加当前实例/工作区引用
    对应 run-service.ts 的 attach
    """
    try:
        instance = InstanceRef.get()
        workspace = WorkspaceRef.get()
        return attach_with(effect_fn, {"instance": instance, "workspace": workspace})
    except Exception:
        return effect_fn


def make_runtime(
    service_name: str,
    layers: list[Any] | None = None,
) -> Runtime:
    """
    创建运行时 (对应 run-service.ts 的 makeRuntime)
    """
    return Runtime(
        service_name=service_name,
        layers=layers or [],
        memo_map=memo_map,
    )


__all__ = [
    "attach_with",
    "attach",
    "make_runtime",
]
