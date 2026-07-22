"""
模型分组 — 移植自 config/model-id.ts
ultra/standard/lite 分级模型组
"""

from __future__ import annotations



MODEL_GROUPS: dict[str, dict] = {
    "ultra": {
        "default": "o1",
        "models": ["o1", "claude-sonnet-4", "gpt-4o"],
        "description": "最强模型，适合复杂任务",
    },
    "standard": {
        "default": "gpt-4o",
        "models": ["gpt-4o", "claude-sonnet-4", "deepseek-v4-flash"],
        "description": "均衡模型，日常使用",
    },
    "lite": {
        "default": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "claude-3-haiku", "llama3"],
        "description": "轻量模型，快速响应",
    },
}


def get_group(name: str) -> dict | None:
    return MODEL_GROUPS.get(name)


def resolve_model(model_ref: str) -> str:
    """解析模型引用，支持分组名"""
    if model_ref in MODEL_GROUPS:
        return MODEL_GROUPS[model_ref]["default"]
    return model_ref


def list_groups() -> list[dict]:
    return [{"name": k, **v} for k, v in MODEL_GROUPS.items()]
