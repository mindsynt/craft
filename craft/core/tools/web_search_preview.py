"""OpenAI Responses API — Web Search Preview tool schemas.

移植自 MiMo-Code packages/opencode/src/provider/sdk/copilot/responses/tool/web-search-preview.ts
"""

from __future__ import annotations

from typing import Any


def web_search_preview_args_schema() -> dict[str, Any]:
    """Return the JSON schema for web search preview args."""
    return {
        "type": "object",
        "properties": {
            "search_context_size": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Search context size (default: medium)",
            },
            "user_location": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["approximate"]},
                    "country": {"type": "string", "description": "Two-letter ISO country code"},
                    "city": {"type": "string"},
                    "region": {"type": "string"},
                    "timezone": {"type": "string", "description": "IANA timezone"},
                },
                "required": ["type"],
            },
        },
    }


def web_search_preview_input_schema() -> dict[str, Any]:
    """Return the JSON schema for web search preview input (action)."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["search"]},
                            "query": {"type": "string"},
                        },
                        "required": ["type"],
                    },
                    {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["open_page"]},
                            "url": {"type": "string"},
                        },
                        "required": ["type", "url"],
                    },
                    {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["find"]},
                            "url": {"type": "string"},
                            "pattern": {"type": "string"},
                        },
                        "required": ["type", "url", "pattern"],
                    },
                ],
            },
        },
    }
