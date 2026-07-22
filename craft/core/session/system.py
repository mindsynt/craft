"""System prompt building — ported from system.ts.

Builds the system prompt for a model based on its provider.
"""

from __future__ import annotations

from typing import Any


# Inline prompt templates (simplified from the TS imports of .txt files)
PROMPT_DEFAULT = """You are Craft Agent, an intelligent coding assistant. You help users with software engineering tasks using the tools available to you. Follow the user's instructions carefully and efficiently."""

PROMPT_ANTHROPIC = """You are Craft Agent, built for Claude. You are an interactive agent that helps users with software engineering tasks."""

PROMPT_GPT = """You are Craft Agent, built for GPT models. You are an interactive agent that helps users with software engineering tasks."""

PROMPT_DEEPSEEK = """You are Craft Agent, powered by DeepSeek. You are an interactive agent that helps users with software engineering tasks."""

PROMPT_GEMINI = """You are Craft Agent, powered by Gemini. You are an interactive agent that helps users with software engineering tasks."""


def provider(model: dict[str, Any]) -> list[str]:
    """Get the appropriate system prompt for a model."""
    api_id = model.get("api", {}).get("id", "").lower()
    if any(x in api_id for x in ["gpt-4", "o1", "o3"]):
        # GPT-4 class → default
        return [PROMPT_DEFAULT]
    if "gpt" in api_id:
        return [PROMPT_GPT]
    if "gemini" in api_id:
        return [PROMPT_GEMINI]
    if "claude" in api_id:
        return [PROMPT_ANTHROPIC]
    if "deepseek" in api_id:
        return [PROMPT_DEEPSEEK]
    return [PROMPT_DEFAULT]


def build_environment_prompt(model: dict[str, Any], now: float, cwd: str, worktree: str) -> list[str]:
    """Build the environment section of the system prompt."""
    import datetime
    import platform

    lines = [
        f"You are Craft Agent. You are an interactive agent that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user.",
        f"You are powered by the model named {model.get('api', {}).get('id', 'unknown')}.",
        "Here is some useful information about the environment you are running in:",
        "<env>",
        f"  Working directory: {cwd}",
        f"  Workspace root folder: {worktree}",
        f"  Platform: {platform.system().lower()}",
        f"  Today's date: {datetime.datetime.fromtimestamp(now / 1000).strftime('%a %b %d %Y')}",
        "</env>",
    ]
    return ["\n".join(lines)]


def build_memory_instructions(session_id: str, memory_root: str) -> str:
    """Build memory system instructions."""
    return f"""# Memory system

You have a persistent file-based memory system. Three file types:

- Session checkpoint at `{os.path.join(memory_root, "sessions", session_id, "checkpoint.md")}` — current session's structured state.
- Project memory at `{os.path.join(memory_root, "projects", "<pid>", "MEMORY.md")}` — persistent across all sessions.
- Global memory at `{os.path.join(memory_root, "global", "MEMORY.md")}` — user-level preferences.

The checkpoint writer is the sole curator of the structured files. You don't maintain them mid-task.

## When to Edit MEMORY.md directly
You may Edit MEMORY.md when:
- User states a project-level rule that should hold across sessions → ## Rules
- User states a project-level architectural decision → ## Architecture decisions
- A clearly durable cross-session fact emerges → ## Discovered durable knowledge"""

import os
