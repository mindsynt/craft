"""Tool script reference — late-bound tool references for tool_script execution.

移植自 MiMo-Code packages/opencode/src/tool/tool-script-ref.ts

tool_script needs the full tool set to dispatch guest RPC calls,
but the registry constructs tool_script itself — this module provides
late-bound references to break the module cycle.
"""

from __future__ import annotations

# Set of tool IDs excluded from tool_script (control-flow / conversation-steering tools)
TOOL_SCRIPT_EXCLUDED: set[str] = {
    "tool_script",
    "invalid",
    "question",
    "task",
    "actor",
    "skill",
    "skill_search",
    "plan_enter",
    "plan_exit",
    "cron",
    "session",
    "workflow",
    "change_directory",
    "bash",
}

# Late-bound reference to the tool definitions, populated at registry init
_tool_script_registry: list | None = None

# Late-bound reference to MCP tools
_tool_script_mcp: dict[str, object] | None = None


def set_tool_registry(defs: list) -> None:
    """Set the tool script registry (called by registry on init)."""
    global _tool_script_registry
    _tool_script_registry = defs


def get_tool_registry() -> list | None:
    """Get the current tool script registry."""
    return _tool_script_registry


def set_mcp_tools(tools: dict[str, object]) -> None:
    """Set MCP tools for tool_script (called by session prompt layer)."""
    global _tool_script_mcp
    _tool_script_mcp = tools


def get_mcp_tools() -> dict[str, object]:
    """Get current MCP tools."""
    return _tool_script_mcp or {}
