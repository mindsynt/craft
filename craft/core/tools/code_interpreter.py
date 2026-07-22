"""OpenAI Responses API — Code Interpreter tool schemas.

移植自 MiMo-Code packages/opencode/src/provider/sdk/copilot/responses/tool/code-interpreter.ts
"""

from __future__ import annotations

from typing import Any, Literal


def code_interpreter_input_schema() -> dict[str, Any]:
    """Return the JSON schema for code interpreter input."""
    return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The code to execute"},
                "container_id": {
                    "type": "string",
                    "description": "The container ID to run code in",
                },
            },
        }


def code_interpreter_output_schema() -> dict[str, Any]:
    """Return the JSON schema for code interpreter output."""
    return {
            "type": "object",
            "properties": {
                "outputs": {
                    "type": "array",
                    "items": {
                        "discriminator": {"propertyName": "type"},
                        "oneOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["logs"]},
                                    "logs": {"type": "string"},
                                },
                                "required": ["type", "logs"],
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["image"]},
                                    "url": {"type": "string"},
                                },
                                "required": ["type", "url"],
                            },
                        ],
                    },
                },
            },
        }


def code_interpreter_args_schema() -> dict[str, Any]:
    """Return the JSON schema for code interpreter args (tool config)."""
    return {
        "type": "object",
        "properties": {
            "container": {
                "oneOf": [
                    {"type": "string", "description": "Container ID"},
                    {
                        "type": "object",
                        "properties": {
                            "file_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                ],
                "description": "Code interpreter container",
            },
        },
    }
