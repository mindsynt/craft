"""Tool result error with metadata.

移植自 MiMo-Code packages/opencode/src/tool/result-error.ts
"""

from __future__ import annotations

from typing import Any


class ToolResultError(Exception):
    """A tool execution error that carries metadata to the persisted error state."""

    def __init__(
        self,
        message: str,
        metadata: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.tool_result_metadata = metadata or {}
        self.tool_result_attachments = attachments or []


def get_tool_result_metadata(error: Any) -> dict[str, Any] | None:
    """Extract metadata from a ToolResultError or similar error-like object."""
    if isinstance(error, ToolResultError):
        return error.tool_result_metadata
    if isinstance(error, dict):
        meta = error.get("toolResultMetadata") or error.get("tool_result_metadata")
        if isinstance(meta, dict):
            return meta
    return None


def get_tool_result_attachments(error: Any) -> list[Any] | None:
    """Extract attachments from a ToolResultError or similar error-like object."""
    if isinstance(error, ToolResultError):
        return error.tool_result_attachments
    if isinstance(error, dict):
        att = error.get("toolResultAttachments") or error.get("tool_result_attachments")
        if isinstance(att, list):
            return att
    return None
