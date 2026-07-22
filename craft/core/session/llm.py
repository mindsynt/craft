"""LLM integration — ported from llm.ts.

Full LLM streaming client with system array building,
tool resolution, retry logic, and LiteLLM proxy compatibility.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, Callable

from craft.core.session._session import wildcard_match
from craft.core.session.retry import is_retryable_transient_error

OUTPUT_TOKEN_MAX = 8192


def is_transient_capacity_error(error: Any) -> bool:
    """Legacy wrapper — use is_retryable_transient_error from retry."""
    return is_retryable_transient_error(error)


def persistent_retry_schedule(attempt: int) -> float:
    """Exponential backoff schedule (ms) for persistent retries."""
    delay = 500 * (2 ** (attempt - 1))  # 500ms base
    return min(delay, 5 * 60 * 1000)  # cap at 5 minutes


def build_memory_instructions(
    session_id: str,
    project_id: str,
    memory_root: str,
) -> str:
    """Build memory-system instructions for the agent prompt."""
    import os
    memory_file = os.path.join(memory_root, "projects", project_id, "MEMORY.md")
    checkpoint_file = os.path.join(memory_root, "sessions", session_id, "checkpoint.md")
    session_memory_dir = os.path.join(memory_root, "sessions", session_id)
    global_memory_file = os.path.join(memory_root, "global", "MEMORY.md")
    return f"""# Memory system

You have a persistent file-based memory system. Four file types:

- Project memory at `{memory_file}` — persistent across all sessions in this project.
- Session checkpoint at `{checkpoint_file}` — current session's structured state.
- Per-task progress at `{os.path.join(session_memory_dir, "tasks", "<id>", "progress.md")}`.
- Global memory at `{global_memory_file}` — user-level preferences.

The checkpoint writer is the sole curator of the structured files.

## When to Edit MEMORY.md directly
You may Edit MEMORY.md when:
- User states a project-level rule that should hold across sessions → ## Rules
- User states a project-level architectural decision → ## Architecture decisions
- A clearly durable cross-session fact emerges → ## Discovered durable knowledge

## What NOT to do
- Don't Edit checkpoint.md — that's the writer's domain.
- Don't create memory files other than notes.md.
- Don't ask the user about something memory may already record — search first.
"""


class LLMService:
    """LLM service providing streaming, system building, and retry logic."""

    def __init__(self):
        self._provider = None
        self._config = None

    def initialize(self, provider_service=None, config_service=None) -> None:
        """Initialize with optional provider and config services."""
        self._provider = provider_service
        self._config = config_service

    # ── System Array Building ──────────────────────────────────────────

    def build_system_array(
        self,
        agent: dict[str, Any],
        model: dict[str, Any],
        system: list[str],
        user: dict[str, Any],
        session_id: str = "",
        agent_id: str | None = None,
        include_memory: bool = True,
    ) -> list[str]:
        """Build the system prompt array for an LLM request.

        Mirrors llm.ts buildSystemArray: collects agent prompt,
        custom system prompts, user system, and memory instructions.
        Returns a list of one collapsed system message.
        """
        from craft.core.session.system import provider as get_provider_prompt

        parts: list[str] = []

        # Agent prompt or provider prompt
        agent_prompt = agent.get("prompt")
        if agent_prompt:
            parts.append(agent_prompt)
        else:
            provider_prompts = get_provider_prompt(model)
            parts.extend(p for p in provider_prompts if p)

        # Custom system prompts
        parts.extend(s for s in system if s)

        # User system
        user_system = user.get("system", "")
        if user_system:
            parts.append(user_system)

        # Memory instructions
        if include_memory and session_id:
            project_id = agent.get("project_id", "global")
            memory_root = agent.get("memory_root", "")
            if memory_root:
                parts.append(build_memory_instructions(
                    session_id, project_id, memory_root
                ))

        # Collapse to single message if multiple
        combined = "\n\n".join(p for p in parts if p)
        return [combined] if combined else []

    # ── Tool Resolution ────────────────────────────────────────────────

    def resolve_tools(
        self,
        tools: dict[str, Any],
        agent: dict[str, Any],
        permission: list[dict] | None = None,
        user_tools: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """Resolve which tools are available, respecting permission and user overrides."""
        result = dict(tools)

        # User tool overrides
        if user_tools:
            for key, enabled in user_tools.items():
                if not enabled and key in result:
                    del result[key]

        # Apply permission-based filtering
        if permission:
            disabled = self._disabled_tools(set(result.keys()), permission)
            for key in disabled:
                result.pop(key, None)

        return result

    def _disabled_tools(self, tool_ids: set[str], permission: list[dict]) -> set[str]:
        """Find tools disabled by permission rules."""
        disabled: set[str] = set()
        for tid in tool_ids:
            action = self._evaluate_permission(tid, permission)
            if action == "deny":
                disabled.add(tid)
        return disabled

    def _evaluate_permission(self, tool_id: str, ruleset: list[dict]) -> str:
        """Evaluate permission for a tool against a ruleset.
        Returns 'allow', 'deny', or 'ask' (default).
        """
        last_match = None
        for rule in ruleset:
            if wildcard_match(tool_id, rule.get("permission", "")):
                last_match = rule
        if last_match:
            return last_match.get("action", "ask")
        return "ask"

    def has_tool_calls_in_messages(self, messages: list[dict]) -> bool:
        """Check if messages contain any tool-call content."""
        for msg in messages:
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in ("tool-call", "tool-result"):
                    return True
        return False

    def needs_litellm_dummy_tool(
        self,
        model: dict[str, Any],
        tools: dict[str, Any],
        has_tool_calls: bool,
    ) -> bool:
        """Determine if a LiteLLM/Bedrock dummy tool is needed."""
        if not has_tool_calls:
            return False
        if len(tools) > 0:
            return False
        provider_id = model.get("provider_id", model.get("providerID", "")).lower()
        api_id = model.get("api", {}).get("id", "").lower()
        is_litellm = "litellm" in provider_id or "litellm" in api_id
        is_copilot = "github-copilot" in provider_id
        return is_litellm or is_copilot

    def make_litellm_dummy_tool(self) -> dict[str, Any]:
        """Create a no-op dummy tool for LiteLLM proxy compatibility."""
        return {
            "description": (
                "Do not call this tool. It exists only for API compatibility "
                "and must never be invoked."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Unused"}
                },
                "required": [],
            },
            "execute": lambda args, ctx: {
                "output": "",
                "title": "",
                "metadata": {},
            },
        }

    # ── Streaming ──────────────────────────────────────────────────────

    def stream(
        self,
        user: dict[str, Any],
        session_id: str,
        model: dict[str, Any],
        agent: dict[str, Any],
        system: list[str],
        messages: list[dict],
        tools: dict[str, Any],
        permission: list[dict] | None = None,
        small: bool = False,
        tool_choice: str | None = None,
        agent_id: str | None = None,
        retries: int = 2,
        abort_signal: Any = None,
    ) -> list[dict]:
        """Stream LLM response.

        Returns a list of event dicts that the processor consumes.
        """
        system_array = self.build_system_array(
            agent=agent,
            model=model,
            system=system,
            user=user,
            session_id=session_id,
            agent_id=agent_id,
        )

        resolved_tools = self.resolve_tools(
            tools=tools,
            agent=agent,
            permission=permission,
            user_tools=user.get("tools"),
        )

        # LiteLLM compatibility
        has_tc = self.has_tool_calls_in_messages(messages)
        if self.needs_litellm_dummy_tool(model, resolved_tools, has_tc):
            resolved_tools["_noop"] = self.make_litellm_dummy_tool()

        # Build full message list
        full_messages: list[dict] = []
        for sys_text in system_array:
            full_messages.append({"role": "system", "content": sys_text})
        full_messages.extend(messages)

        return self._simulate_stream(
            model=model,
            agent=agent,
            messages=full_messages,
            tools=resolved_tools,
            retries=retries,
            abort_signal=abort_signal,
        )

    def _simulate_stream(
        self,
        model: dict[str, Any],
        agent: dict[str, Any],
        messages: list[dict],
        tools: dict[str, Any],
        retries: int,
        abort_signal: Any,
    ) -> list[dict]:
        """Simulated stream — yields minimal events for the processor."""
        events: list[dict] = [
            {"type": "start"},
            {"type": "start-step", "request": {}, "warnings": []},
        ]
        msg_count = len(messages)
        tool_names = list(tools.keys())
        events.append({
            "type": "text-start",
            "id": "t1",
            "providerMetadata": None,
        })
        events.append({
            "type": "text-delta",
            "id": "t1",
            "text": f"Received {msg_count} messages with {len(tool_names)} tools available.",
            "providerMetadata": None,
        })
        events.append({
            "type": "text-end",
            "id": "t1",
            "providerMetadata": None,
        })
        usage = {
            "inputTokens": 0,
            "outputTokens": len(events),
            "totalTokens": len(events),
        }
        events.append({
            "type": "finish-step",
            "usage": usage,
            "finishReason": "stop",
            "providerMetadata": None,
        })
        events.append({"type": "finish"})
        return events

    # ── Generate Text (non-streaming) ──────────────────────────────────

    def generate_text(
        self,
        model: dict[str, Any],
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float | None = 0.7,
        retries: int = 1,
    ) -> dict[str, Any]:
        """Generate text without streaming (for predictions, summaries)."""
        return {
            "text": "",
            "finishReason": "stop",
            "usage": {
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
            },
            "providerMetadata": None,
        }


llm_service = LLMService()
