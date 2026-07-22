"""OpenAI Responses API — File Search tool schemas.

移植自 MiMo-Code packages/opencode/src/provider/sdk/copilot/responses/tool/file-search.ts
"""

from __future__ import annotations

from typing import Any


def comparison_filter_schema() -> dict[str, Any]:
    """Return the JSON schema for a comparison filter."""
    return {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "type": {"type": "string", "enum": ["eq", "ne", "gt", "gte", "lt", "lte"]},
            "value": {"oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]},
        },
        "required": ["key", "type", "value"],
    }


def compound_filter_schema() -> dict[str, Any]:
    """Return the JSON schema for a compound (AND/OR) filter."""
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["and", "or"]},
            "filters": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"$ref": "#/$defs/comparisonFilter"},
                        {"$ref": "#/$defs/compoundFilter"},
                    ],
                },
            },
        },
        "required": ["type", "filters"],
    }


def file_search_args_schema() -> dict[str, Any]:
    """Return the JSON schema for file search args."""
    return {
        "type": "object",
        "properties": {
            "vector_store_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of vector store IDs to search through",
            },
            "max_num_results": {
                "type": "integer",
                "description": "Maximum number of results (default 10)",
            },
            "ranking": {
                "type": "object",
                "properties": {
                    "ranker": {"type": "string"},
                    "score_threshold": {"type": "number"},
                },
            },
            "filters": {
                "oneOf": [
                    comparison_filter_schema(),
                    compound_filter_schema(),
                ],
                "description": "Filters to apply to the search",
            },
        },
        "required": ["vector_store_ids"],
    }


def file_search_output_schema() -> dict[str, Any]:
    """Return the JSON schema for file search output."""
    return {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Search queries executed",
            },
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "attributes": {
                            "type": "object",
                            "additionalProperties": {},
                            "description": "Key-value pairs attached to the file",
                        },
                        "file_id": {"type": "string"},
                        "filename": {"type": "string"},
                        "score": {"type": "number"},
                        "text": {"type": "string"},
                    },
                    "required": ["file_id", "filename", "score", "text"],
                },
            },
        },
        "required": ["queries"],
    }
