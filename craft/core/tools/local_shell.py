"""OpenAI Responses API — Local Shell tool schemas.

移植自 MiMo-Code packages/opencode/src/provider/sdk/copilot/responses/tool/local-shell.ts
"""

from __future__ import annotations

from typing import Any


def local_shell_input_schema() -> dict[str, Any]:
    """Return the JSON schema for local shell tool input."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["exec"]},
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The command to run",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Optional timeout in milliseconds",
                    },
                    "user": {
                        "type": "string",
                        "description": "Optional user to run as",
                    },
                    "working_directory": {
                        "type": "string",
                        "description": "Optional working directory",
                    },
                    "env": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Environment variables",
                    },
                },
                "required": ["type", "command"],
            },
        },
        "required": ["action"],
    }


def local_shell_output_schema() -> dict[str, Any]:
    """Return the JSON schema for local shell tool output."""
    return {
        "type": "object",
        "properties": {
            "output": {
                "type": "string",
                "description": "The command output",
            },
        },
        "required": ["output"],
    }
