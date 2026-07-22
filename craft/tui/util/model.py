"""
模型选择 — 移植自 util/model.ts

Provider/Model 列表的索引、查找和显示名称。
"""

from __future__ import annotations

from typing import Any


def index(providers: list[dict] | None) -> dict[str, dict]:
    """将 provider 列表建立为 id→provider 的字典"""
    return {(p.get("id", "")): p for p in (providers or []) if isinstance(p, dict)}


def get(
    providers: list[dict] | dict[str, dict] | None,
    provider_id: str,
    model_id: str,
) -> dict | None:
    """获取指定 provider/model 的 model 配置"""
    if isinstance(providers, dict):
        provider = providers.get(provider_id)
    elif isinstance(providers, list):
        provider = next((p for p in providers if p.get("id") == provider_id), None)
    else:
        return None
    if provider and isinstance(provider, dict):
        models = provider.get("models", {})
        if isinstance(models, dict):
            return models.get(model_id)
    return None


def name(
    providers: list[dict] | dict[str, dict] | None,
    provider_id: str,
    model_id: str,
) -> str:
    """获取模型显示名称"""
    model = get(providers, provider_id, model_id)
    if model and isinstance(model, dict):
        display = model.get("name")
        if isinstance(display, str) and display:
            return display
    return model_id
