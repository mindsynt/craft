"""Copilot provider helpers"""

from __future__ import annotations

from typing import Any


def get_copilot_metadata(part_or_message: dict[str, Any]) -> dict[str, Any]:
    """Extract Copilot metadata from a message or part's providerOptions.

    This is an alias for get_openai_metadata provided for semantic clarity
    when working with Copilot-specific features (reasoningOpaque, etc.).
    """
    from craft.core.provider.transform import get_openai_metadata

    return get_openai_metadata(part_or_message)
