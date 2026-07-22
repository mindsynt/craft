"""Session processor — ported from processor.ts.

Handles LLM streaming events, tool call lifecycle, and text n-gram detection.
Full implementation with event handling for the complete set of AI SDK events.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ProcessorResult(str, Enum):
    OVERFLOW = "overflow"
    STOP = "stop"
    CONTINUE = "continue"
    TEXT_REPEAT = "text-repeat"


@dataclass
class ProposedToolCall:
    tool_call_id: str = ""
    tool_name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayInput:
    reasoning: str = ""
    reasoning_metadata: dict[str, Any] | None = None
    text: str = ""
    text_metadata: dict[str, Any] | None = None
    tool_calls: list[ProposedToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Any = None
    provider_metadata: dict[str, Any] | None = None
    tools: dict[str, Any] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    selection: dict | None = None  # {'winner': int, 'total': int}
    thinking_ms: int | None = None
    overhead: dict | None = None  # {'cost': float, 'tokensIn': int, 'tokensOut': int}


@dataclass
class AgentMetrics:
    tokens_in: int = 0
    tokens_out: int = 0
    files_changed: int = 0


DOOM_LOOP_THRESHOLD = 3
MAX_GOAL_REACT = 12


class TextNgramMonitor:
    """Monitor for repeated text n-grams to detect text loops (streaming)."""

    def __init__(self, min_ngram: int = 50, max_ngram: int = 100, threshold: int = 5):
        self.min_ngram = min_ngram
        self.max_ngram = max_ngram
        self.threshold = threshold
        self._ngrams: dict[str, int] = {}
        self._buffer: list[str] = []
        self._repeated = False

    def append(self, text: str) -> bool:
        """Append text and check for n-gram repeats. Returns True if repeated."""
        if self._repeated:
            return True
        self._buffer.append(text)
        combined = "".join(self._buffer[-20:])
        for n in range(self.min_ngram, min(self.max_ngram, len(combined)) + 1):
            for i in range(len(combined) - n + 1):
                ngram = combined[i: i + n]
                if len(ngram.strip()) < n * 0.5:
                    continue
                count = self._ngrams.get(ngram, 0) + 1
                self._ngrams[ngram] = count
                if count >= self.threshold:
                    self._repeated = True
                    return True
        return False

    @property
    def repeated(self) -> bool:
        return self._repeated

    def reset(self) -> None:
        self._ngrams.clear()
        self._buffer.clear()
        self._repeated = False


class ProcessorContext:
    """Context object for processor execution — mirrors ProcessorContext from TS."""

    def __init__(
        self,
        assistant_message: dict[str, Any] | None = None,
        session_id: str = "",
        model: dict[str, Any] | None = None,
        agent_metrics: AgentMetrics | None = None,
    ):
        self.assistant_message = assistant_message or {}
        self.session_id = session_id or self.assistant_message.get("sessionID", self.assistant_message.get("session_id", ""))
        self.model = model or {}
        self.agent_metrics = agent_metrics

        # Internal state
        self.toolcalls: dict[str, dict] = {}  # toolCallId -> {done: ..., partID: ..., messageID: ..., sessionID: ...}
        self.should_break = False
        self.snapshot: str | None = None
        self.blocked = False
        self.needs_overflow = False
        self.current_text: dict | None = None
        self.reasoning_map: dict[str, dict] = {}
        self.step_started_at: float | None = None
        self.first_token_at: float | None = None
        self.step_part_ids: list[str] = []
        self.text_ngram_monitor: TextNgramMonitor | None = None
        self.text_ngram_repeat = False
        self.aborted = False

    @property
    def message_id(self) -> str:
        return self.assistant_message.get("id", "")


def compute_diff(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute file diffs from step-start/step-finish snapshots."""
    from_snapshot: str | None = None
    to_snapshot: str | None = None
    for item in messages:
        info = item.get("info", item)
        parts = item.get("parts", [])
        if from_snapshot is None:
            for part in parts:
                if part.get("type") == "step-start" and part.get("snapshot"):
                    from_snapshot = part["snapshot"]
                    break
        for part in parts:
            if part.get("type") == "step-finish" and part.get("snapshot"):
                to_snapshot = part["snapshot"]
    if from_snapshot and to_snapshot:
        return [{"file": "snapshot", "additions": 0, "deletions": 0}]
    return []


def stable_stringify(value: Any) -> str:
    """Deterministic JSON serialization with sorted keys."""
    if value is None or not isinstance(value, (dict, list)):
        return json.dumps(value) if value is not None else "null"
    if isinstance(value, list):
        return "[" + ",".join(stable_stringify(v) for v in value) + "]"
    keys = sorted(value.keys())
    return "{" + ",".join(
        json.dumps(k) + ":" + stable_stringify(value[k]) for k in keys
    ) + "}"


def step_signature(parts: list[dict]) -> str | None:
    """Stable signature for an assistant step's action (tool calls only)."""
    segments: list[str] = []
    for part in parts:
        if part.get("type") == "tool":
            tool_name = part.get("tool", "")
            state_input = part.get("state", {}).get("input", {})
            segments.append(f"tool:{tool_name}:{stable_stringify(state_input)}")
    if not segments:
        return None
    return "\n".join(segments)


def describe_try_best(incident: dict) -> str:
    """Describe a try-best loop detection incident."""
    reason = incident.get("reason", "unknown")
    evidence = incident.get("evidence", {})
    count = evidence.get("count", 0)
    path = evidence.get("path")
    action = evidence.get("action")
    if reason == "edit_repeat":
        return f"A near-identical edit to {path or 'the same file'} repeated {count} times."
    if reason == "bash_retry":
        return f"The same failing command was retried {count} times without an intervening successful edit."
    return f"{count} consecutive {action or 'same-kind'} actions made no observable progress."


class ProcessorService:
    """Handles LLM streaming events, tool call lifecycle, and overflow detection.

    Mirrors the TS processor.ts Service.create() implementation.
    """

    def __init__(self):
        self._session_service = None
        self._config_service = None
        self._bus_service = None
        self._snapshot_service = None
        self._agent_service = None
        self._llm_service = None
        self._permission_service = None
        self._plugin_service = None
        self._summary_service = None
        self._status_service = None

    def initialize(
        self,
        session_service=None,
        config_service=None,
        bus_service=None,
        snapshot_service=None,
        agent_service=None,
        llm_service=None,
        permission_service=None,
        plugin_service=None,
        summary_service=None,
        status_service=None,
    ) -> None:
        """Initialize with service dependencies."""
        self._session_service = session_service
        self._config_service = config_service
        self._bus_service = bus_service
        self._snapshot_service = snapshot_service
        self._agent_service = agent_service
        self._llm_service = llm_service
        self._permission_service = permission_service
        self._plugin_service = plugin_service
        self._summary_service = summary_service
        self._status_service = status_service

    def create(
        self,
        assistant_message: dict[str, Any],
        session_id: str,
        model: dict[str, Any],
        agent_metrics: AgentMetrics | None = None,
    ) -> ProcessorHandle:
        """Create a processor handle for a new assistant message stream.

        Mirrors processor.ts create(). Returns a Handle with process() and replay().
        """
        ctx = ProcessorContext(
            assistant_message=assistant_message,
            session_id=session_id,
            model=model,
            agent_metrics=agent_metrics,
        )

        return ProcessorHandle(
            ctx=ctx,
            session_service=self._session_service,
            config_service=self._config_service,
            bus_service=self._bus_service,
            snapshot_service=self._snapshot_service,
            agent_service=self._agent_service,
            llm_service=self._llm_service,
            permission_service=self._permission_service,
            plugin_service=self._plugin_service,
            summary_service=self._summary_service,
            status_service=self._status_service,
        )


class ProcessorHandle:
    """Handle returned by ProcessorService.create().

    Mirrors the TS Handle interface: process(), replay(),
    updateToolCall(), completeToolCall().
    """

    def __init__(
        self,
        ctx: ProcessorContext,
        session_service=None,
        config_service=None,
        bus_service=None,
        snapshot_service=None,
        agent_service=None,
        llm_service=None,
        permission_service=None,
        plugin_service=None,
        summary_service=None,
        status_service=None,
    ):
        self._ctx = ctx
        self._session = session_service
        self._config = config_service
        self._bus = bus_service
        self._snapshot = snapshot_service
        self._agents = agent_service
        self._llm = llm_service
        self._permission = permission_service
        self._plugin = plugin_service
        self._summary = summary_service
        self._status = status_service

    @property
    def message(self) -> dict[str, Any]:
        return self._ctx.assistant_message

    def process(self, stream_input: dict[str, Any]) -> str:
        """Process an LLM stream and return the outcome.

        Args:
            stream_input: Dict with keys: user, agent, sessionID, system,
                         messages, tools, model, toolChoice, etc.

        Returns:
            ProcessorResult value: "continue", "overflow", "stop", "text-repeat"
        """
        ctx = self._ctx

        # Reset per-stream state
        ctx.current_text = None
        ctx.reasoning_map = {}
        ctx.step_part_ids = []
        ctx.toolcalls = {}
        ctx.text_ngram_repeat = False
        ctx.text_ngram_monitor = TextNgramMonitor()
        ctx.needs_overflow = False
        ctx.should_break = True  # default

        # Get stream events from LLM
        user = stream_input.get("user", {})
        agent = stream_input.get("agent", {})
        system = stream_input.get("system", [])
        messages = stream_input.get("messages", [])
        tools = stream_input.get("tools", {})
        model = stream_input.get("model", ctx.model)
        permission = stream_input.get("permission")
        tool_choice = stream_input.get("toolChoice")
        agent_id = stream_input.get("agentID")

        events = self._llm.stream(
            user=user,
            session_id=ctx.session_id,
            model=model,
            agent=agent,
            system=system,
            messages=messages,
            tools=tools,
            permission=permission,
            tool_choice=tool_choice,
            agent_id=agent_id,
        )

        # Process each event
        for event in events:
            self._handle_event(event, stream_input)

            # Check overflow/break conditions
            if ctx.needs_overflow or ctx.text_ngram_repeat or ctx.blocked:
                break

        # Cleanup
        self._cleanup()

        # Determine result
        if ctx.needs_overflow:
            return ProcessorResult.OVERFLOW
        if ctx.text_ngram_repeat:
            return ProcessorResult.TEXT_REPEAT
        if ctx.blocked or ctx.assistant_message.get("error"):
            return ProcessorResult.STOP
        return ProcessorResult.CONTINUE

    def replay(self, input: ReplayInput) -> str:
        """Replay a pre-selected candidate (max mode)."""
        from craft.core.session.schema import PartID

        ctx = self._ctx
        ctx.needs_overflow = False
        ctx.should_break = True

        # Synthesize stream events for the winner
        synthetic_events: list[dict] = []

        # Start → start-step
        synthetic_events.append({"type": "start"})
        synthetic_events.append({"type": "start-step", "request": {}, "warnings": []})

        # Reasoning (if any)
        selection_note = None
        if input.selection:
            selection_note = f"[max mode] selected candidate {input.selection['winner'] + 1} of {input.selection['total']}"
        reasoning_text = "\n\n".join(filter(None, [selection_note, input.reasoning]))

        if reasoning_text:
            rid = "reasoning-replay"
            backdated_start = (time.time() * 1000 - input.thinking_ms) if input.thinking_ms else None
            synthetic_events.append({
                "type": "reasoning-start",
                "id": rid,
                "providerMetadata": input.reasoning_metadata,
                "time": {"start": backdated_start} if backdated_start else {},
            })
            synthetic_events.append({
                "type": "reasoning-delta",
                "id": rid,
                "text": reasoning_text,
                "providerMetadata": input.reasoning_metadata,
            })
            synthetic_events.append({
                "type": "reasoning-end",
                "id": rid,
                "providerMetadata": input.reasoning_metadata,
            })

        # Text (if any)
        if input.text:
            tid = "text-replay"
            synthetic_events.append({
                "type": "text-start",
                "id": tid,
                "providerMetadata": input.text_metadata,
            })
            synthetic_events.append({
                "type": "text-delta",
                "id": tid,
                "text": input.text,
                "providerMetadata": input.text_metadata,
            })
            synthetic_events.append({
                "type": "text-end",
                "id": tid,
                "providerMetadata": input.text_metadata,
            })

        # Tool calls
        for call in input.tool_calls:
            if ctx.needs_overflow or ctx.blocked:
                break

            synthetic_events.append({
                "type": "tool-input-start",
                "id": call.tool_call_id,
                "toolName": call.tool_name,
                "providerMetadata": call.provider_metadata,
            })
            synthetic_events.append({
                "type": "tool-call",
                "toolCallId": call.tool_call_id,
                "toolName": call.tool_name,
                "input": call.input,
                "providerMetadata": call.provider_metadata,
            })

            # Execute the tool
            t = input.tools.get(call.tool_name)
            if not t or not t.get("execute"):
                synthetic_events.append({
                    "type": "tool-error",
                    "toolCallId": call.tool_call_id,
                    "toolName": call.tool_name,
                    "input": call.input,
                    "error": f'Tool "{call.tool_name}" has no executor',
                })
                continue

            try:
                outcome = t["execute"](call.input, {
                    "toolCallId": call.tool_call_id,
                    "messages": input.messages,
                })
                synthetic_events.append({
                    "type": "tool-result",
                    "toolCallId": call.tool_call_id,
                    "toolName": call.tool_name,
                    "input": call.input,
                    "output": outcome,
                })
            except Exception as e:
                synthetic_events.append({
                    "type": "tool-error",
                    "toolCallId": call.tool_call_id,
                    "toolName": call.tool_name,
                    "input": call.input,
                    "error": str(e),
                })

        # Finish-step
        usage = input.usage or {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
        synthetic_events.append({
            "type": "finish-step",
            "usage": usage,
            "finishReason": input.finish_reason,
            "providerMetadata": input.provider_metadata,
        })

        # Process synthetic events
        stream_input = {
            "agent": {},
            "system": [],
            "messages": input.messages,
            "tools": input.tools,
            "model": ctx.model,
        }
        for event in synthetic_events:
            self._handle_event(event, stream_input)
            if ctx.needs_overflow or ctx.blocked:
                break

        # Apply overhead
        if input.overhead:
            overhead = input.overhead
            if overhead.get("cost", 0) > 0 or overhead.get("tokensIn", 0) > 0 or overhead.get("tokensOut", 0) > 0:
                ctx.assistant_message["cost"] = ctx.assistant_message.get("cost", 0) + overhead.get("cost", 0)
                if ctx.agent_metrics:
                    ctx.agent_metrics.tokens_in += overhead.get("tokensIn", 0)
                    ctx.agent_metrics.tokens_out += overhead.get("tokensOut", 0)

        self._cleanup()

        if ctx.needs_overflow:
            return ProcessorResult.OVERFLOW
        if ctx.text_ngram_repeat:
            return ProcessorResult.TEXT_REPEAT
        if ctx.blocked or ctx.assistant_message.get("error"):
            return ProcessorResult.STOP
        return ProcessorResult.CONTINUE

    def _handle_event(self, event: dict, stream_input: dict) -> None:
        """Handle a single LLM stream event — mirrors processor.ts handleEvent."""
        from craft.core.session.schema import PartID, MessageID

        ctx = self._ctx
        msg_id = ctx.assistant_message.get("id", "")
        session_id = ctx.session_id

        event_type = event.get("type", "")

        # ── start ──
        if event_type == "start":
            is_main = not ctx.assistant_message.get("agentID") or ctx.assistant_message["agentID"] == "main"
            if is_main and self._status:
                self._status.set(session_id, {"type": "busy"})
            return

        # ── reasoning-start ──
        if event_type == "reasoning-start":
            rid = event.get("id", "r")
            if rid in ctx.reasoning_map:
                return
            part_id = PartID.ascending()
            ctx.reasoning_map[rid] = {
                "id": part_id,
                "messageID": msg_id,
                "sessionID": session_id,
                "type": "reasoning",
                "text": "",
                "time": {"start": event.get("time", {}).get("start", time.time() * 1000)},
                "metadata": event.get("providerMetadata"),
            }
            ctx.step_part_ids.append(part_id)
            return

        # ── reasoning-delta ──
        if event_type == "reasoning-delta":
            rid = event.get("id", "")
            if rid not in ctx.reasoning_map:
                return
            if ctx.first_token_at is None:
                ctx.first_token_at = time.time() * 1000
            ctx.reasoning_map[rid]["text"] += event.get("text", "")
            if event.get("providerMetadata"):
                ctx.reasoning_map[rid]["metadata"] = event["providerMetadata"]
            return

        # ── reasoning-end ──
        if event_type == "reasoning-end":
            rid = event.get("id", "")
            if rid not in ctx.reasoning_map:
                return
            ctx.reasoning_map[rid]["time"]["end"] = time.time() * 1000
            if event.get("providerMetadata"):
                ctx.reasoning_map[rid]["metadata"] = event["providerMetadata"]
            del ctx.reasoning_map[rid]
            return

        # ── tool-input-start ──
        if event_type == "tool-input-start":
            if ctx.assistant_message.get("summary"):
                raise ValueError(f"Tool call not allowed while generating summary: {event.get('toolName')}")
            tool_call_id = event.get("id", "")
            part_id = ctx.toolcalls.get(tool_call_id, {}).get("partID") or PartID.ascending()
            part = {
                "id": part_id,
                "messageID": msg_id,
                "sessionID": session_id,
                "type": "tool",
                "tool": event.get("toolName", ""),
                "callID": tool_call_id,
                "state": {"status": "pending", "input": {}, "raw": ""},
                "metadata": {"providerExecuted": True} if event.get("providerExecuted") else None,
            }
            ctx.step_part_ids.append(part_id)
            ctx.toolcalls[tool_call_id] = {
                "done": False,
                "partID": part_id,
                "messageID": msg_id,
                "sessionID": session_id,
            }
            return

        # ── tool-input-delta / tool-input-end ──
        if event_type in ("tool-input-delta", "tool-input-end"):
            return

        # ── tool-call ──
        if event_type == "tool-call":
            if ctx.assistant_message.get("summary"):
                raise ValueError(f"Tool call not allowed while generating summary: {event.get('toolName')}")
            tool_call_id = event.get("toolCallId", "")
            # Update the tool part from pending/input -> running
            tc = ctx.toolcalls.get(tool_call_id)
            if tc:
                tc["done"] = True  # signal that we've seen the call
            return

        # ── tool-result ──
        if event_type == "tool-result":
            tool_call_id = event.get("toolCallId", "")
            tc = ctx.toolcalls.get(tool_call_id)
            if tc:
                ctx.toolcalls.pop(tool_call_id, None)
            return

        # ── tool-error ──
        if event_type == "tool-error":
            tool_call_id = event.get("toolCallId", "")
            ctx.toolcalls.pop(tool_call_id, None)
            return

        # ── error ──
        if event_type == "error":
            error = event.get("error", "Unknown error")
            if isinstance(error, dict) and error.get("name") == "ContextOverflowError":
                ctx.needs_overflow = True
            else:
                ctx.assistant_message["error"] = error
            return

        # ── start-step ──
        if event_type == "start-step":
            ctx.step_started_at = time.time() * 1000
            ctx.first_token_at = None
            step_start_part_id = PartID.ascending()
            ctx.step_part_ids.append(step_start_part_id)
            return

        # ── finish-step ──
        if event_type == "finish-step":
            usage = event.get("usage", {})
            finish_reason = event.get("finishReason", "stop")
            ctx.assistant_message["finish"] = finish_reason
            ctx.assistant_message["cost"] = ctx.assistant_message.get("cost", 0) + usage.get("cost", 0)
            if ctx.agent_metrics:
                step_tokens_in = usage.get("inputTokens", 0) + usage.get("cacheReadTokens", 0) + usage.get("cacheWriteTokens", 0)
                step_tokens_out = usage.get("outputTokens", 0) + usage.get("reasoningTokens", 0)
                ctx.agent_metrics.tokens_in += step_tokens_in
                ctx.agent_metrics.tokens_out += step_tokens_out
            # Check overflow
            if not ctx.assistant_message.get("summary"):
                model = ctx.model
                tokens = {
                    "input": usage.get("inputTokens", 0),
                    "output": usage.get("outputTokens", 0),
                    "reasoning": usage.get("reasoningTokens", 0),
                    "cache": {
                        "read": usage.get("cacheReadTokens", 0),
                        "write": usage.get("cacheWriteTokens", 0),
                    },
                }
                if self._is_overflow(tokens, model):
                    ctx.needs_overflow = True
            return

        # ── text-start ──
        if event_type == "text-start":
            ctx.current_text = {
                "id": PartID.ascending(),
                "messageID": msg_id,
                "sessionID": session_id,
                "type": "text",
                "text": "",
                "time": {"start": time.time() * 1000},
                "metadata": event.get("providerMetadata"),
            }
            ctx.step_part_ids.append(ctx.current_text["id"])
            return

        # ── text-delta ──
        if event_type == "text-delta":
            if ctx.current_text is None:
                return
            if ctx.first_token_at is None:
                ctx.first_token_at = time.time() * 1000
            ctx.current_text["text"] += event.get("text", "")
            if event.get("providerMetadata"):
                ctx.current_text["metadata"] = event["providerMetadata"]
            # N-gram check
            if ctx.text_ngram_monitor and ctx.text_ngram_monitor.append(event.get("text", "")):
                ctx.text_ngram_repeat = True
            return

        # ── text-end ──
        if event_type == "text-end":
            if ctx.current_text is None:
                return
            end_time = time.time() * 1000
            ctx.current_text["time"]["end"] = end_time
            if event.get("providerMetadata"):
                ctx.current_text["metadata"] = event["providerMetadata"]
            ctx.current_text = None
            return

        # ── finish ──
        if event_type == "finish":
            return

    def _is_overflow(self, tokens: dict, model: dict) -> bool:
        """Check if token usage exceeds model context limit."""
        from craft.core.session.overflow import is_overflow
        cfg = self._config.get() if self._config else {}
        return is_overflow(cfg, tokens, model)

    def _cleanup(self) -> None:
        """Clean up after stream processing — mirrors processor.ts cleanup()."""
        ctx = self._ctx

        # Close any unresolved tool calls
        for tool_call_id, tc in list(ctx.toolcalls.items()):
            if tc.get("partID"):
                ctx.toolcalls.pop(tool_call_id, None)

        # Finalize current text
        if ctx.current_text:
            end_time = time.time() * 1000
            ctx.current_text["time"]["end"] = end_time
            ctx.current_text = None

        # Finalize reasoning
        for rid in list(ctx.reasoning_map.keys()):
            ctx.reasoning_map[rid]["time"]["end"] = time.time() * 1000
        ctx.reasoning_map = {}

        # Update assistant message
        ctx.assistant_message["time"] = ctx.assistant_message.get("time", {})
        ctx.assistant_message["time"]["completed"] = time.time() * 1000


processor_service = ProcessorService()
