"""Provider registry & factory"""

from __future__ import annotations

from typing import Any

from craft.core.provider.base import BaseProvider, ProviderError
from craft.core.provider.openai_compatible import OpenAIProvider
from craft.core.provider.openai_responses import OpenAIResponsesProvider
from craft.core.provider.anthropic import AnthropicProvider
from craft.core.provider.openai_config import ProviderSettings
from craft.config import get_config


PROVIDER_MAP: dict[str, Any] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "openai-responses": OpenAIResponsesProvider,
    "ollama": lambda **kw: OpenAIProvider(base_url="http://localhost:11434/v1", **kw),
}


def register_provider(name: str, factory: Any) -> None:
    """Register a custom provider factory."""
    PROVIDER_MAP[name] = factory


def get_provider(
    provider_name: str | None = None,
    model: str | None = None,
    settings: ProviderSettings | None = None,
) -> BaseProvider:
    cfg = get_config()
    if model and "/" in model:
        provider_name, model = model.split("/", 1)
    provider_name = provider_name or "openai"
    defaults = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4",
        "ollama": "llama3",
        "openai-responses": "gpt-4o",
    }
    model = model or defaults.get(provider_name, "")
    factory = PROVIDER_MAP.get(provider_name)
    if not factory:
        raise ProviderError(
            f"未知提供商: {provider_name}，可用: {', '.join(PROVIDER_MAP.keys())}",
            400,
        )

    # Apply settings from config
    settings_dict: dict[str, Any] = {"model": model}
    if settings:
        settings_dict.update(settings)

    return factory(**settings_dict)
