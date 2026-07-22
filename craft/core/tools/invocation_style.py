"""Invocation style resolution — 移植自 packages/opencode/src/tool/invocation-style.ts

Single source of truth for "which invocation style is tool <toolId> in".
Per-tool override wins; otherwise the global default; otherwise "json".
"""

from __future__ import annotations

from typing import Literal

InvocationStyle = Literal["json", "shell"]


def resolve_invocation_style(
    cfg: dict | None,
    tool_id: str,
) -> InvocationStyle:
    """Resolve invocation style for a given tool.

    Args:
        cfg: Config dict with optional "tool" block containing
             "invocation_style" (global default) and/or
             "invocation_style_by_tool" (per-tool overrides).
        tool_id: The tool ID (e.g., "bash", "read", "write").

    Returns:
        "json" or "shell".
    """
    if cfg is None:
        return "json"

    tool_cfg = cfg.get("tool", {})
    if not isinstance(tool_cfg, dict):
        return "json"

    by_tool = tool_cfg.get("invocation_style_by_tool", {})
    if isinstance(by_tool, dict) and tool_id in by_tool:
        return by_tool[tool_id]

    default_style = tool_cfg.get("invocation_style", "json")
    if default_style in ("json", "shell"):
        return default_style

    return "json"
