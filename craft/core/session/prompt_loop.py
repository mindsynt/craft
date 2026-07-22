"""Session prompt loop — ported from prompt.ts.

Main session orchestration: creates user messages, manages the run loop,
resolves tools, handles overflow, text loops, goal gates, and step
classification. This is the core of the session system.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

from craft.core.session.classify import classify_assistant_step
from craft.core.session.goal import goal_manager, JUDGE_SYSTEM, judge_user_prompt
from craft.core.session.prompt.text_loop_recovery import (
    TEXT_LOOP_BUFFER_SIZE,
    TEXT_LOOP_TRIGGER_COUNT,
    TEXT_LOOP_MAX_RECOVERY,
    normalize_for_loop_detection,
    detect_text_loop,
    RECOVERY_PROMPT_MILD,
    RECOVERY_PROMPT_STRONG,
)
from craft.core.session.prompt.text_ngram_detection import (
    TEXT_NGRAM_MAX_RECOVERY,
    TEXT_NGRAM_RECOVERY_REMIND,
    TEXT_NGRAM_RECOVERY_REPLAN,
    create_text_ngram_monitor,
    TextNgramMonitor,
)
from craft.core.session.prompt.empty_step_detection import (
    EMPTY_STEP_MAX_RECOVERY,
    EMPTY_STEP_RECOVERY_REMIND,
    EMPTY_STEP_RECOVERY_REPLAN,
    is_empty_step,
)
from craft.core.session.trajectory import (
    serialize_trajectory_messages,
    with_assistant_parts,
    user_query_text,
    assistant_final_text,
    session_error_text,
)
from craft.core.session.message import TextPart, ToolPart, MessageWithParts
from craft.core.session.schema import SessionID, MessageID, PartID
from craft.core.session.llm import llm_service
from craft.core.session.processor import (
    processor_service,
    ProcessorHandle,
    ProcessorResult,
    ProcessorService,
)
from craft.core.session.status import session_status
from craft.core.session._session import sessions


# ── Constants ──────────────────────────────────────────────────────────

ORCHESTRATOR_TITLE = "Orchestrator"
MAX_GOAL_REACT = 12
REPEATED_STEP_THRESHOLD = 3
OUTPUT_LENGTH_CONTINUATION_LIMIT = 3
INVALID_OUTPUT_CONTINUATION_LIMIT = 2
TEXT_TOOL_CALL_RETRY_LIMIT = 2

STRUCTURED_OUTPUT_DESCRIPTION = (
    "Use this tool to return your final response in the requested structured format.\n\n"
    "IMPORTANT:\n"
    "- You MUST call this tool exactly once at the end of your response\n"
    "- The input must be valid JSON matching the required schema\n"
    "- Complete all necessary research and tool calls BEFORE calling this tool\n"
    "- This tool provides your final answer - no further actions are taken after calling it"
)

STRUCTURED_OUTPUT_SYSTEM_PROMPT = (
    "IMPORTANT: The user has requested structured output. You MUST use the "
    "StructuredOutput tool to provide your final response. Do NOT respond with "
    "plain text - you MUST call the StructuredOutput tool with your answer "
    "formatted according to the schema."
)

PREDICT_SYSTEM = (
    "You predict the single most likely next message a user will send to a "
    "coding assistant, based on the conversation so far. Output only that next "
    "message as one short, natural first-person request (what the user would type). "
    "No preamble, no quotes, no explanation, no markdown. Keep it under 100 characters."
)

PREDICT_NUDGE = "Based on the conversation above, write the user's most likely next message:"

MAX_STEPS_TEXT = (
    "<system-reminder>\n"
    "You have reached the maximum number of steps for this turn. "
    "Provide your final answer now — do not make additional tool calls.\n"
    "</system-reminder>"
)

BUILD_SWITCH_TEXT = (
    "<system-reminder>\n"
    "Build mode is active. When you execute, use the write and edit tools to modify files.\n"
    "</system-reminder>"
)


# ── Helper Functions ──────────────────────────────────────────────────


def stable_root_title(agent: str | None, parent_id: str | None) -> str | None:
    """Determine if a session should get a stable root title."""
    if parent_id:
        return None
    if agent == "orchestrator":
        return ORCHESTRATOR_TITLE
    return None


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


def nudged_since_boundary(
    msgs: list[dict], boundary_id: str | None, marker: str
) -> bool:
    """Check if a nudge has already been injected since the last checkpoint boundary."""
    if boundary_id:
        boundary_idx = -1
        for i, m in enumerate(msgs):
            info = m.get("info", m)
            if info.get("id") == boundary_id:
                boundary_idx = i
                break
        episode = msgs[boundary_idx:] if boundary_idx >= 0 else msgs
    else:
        episode = msgs
    for m in episode:
        parts = m.get("parts", [])
        for p in parts:
            if p.get("type") == "text" and marker in p.get("text", ""):
                return True
    return False


def recall_hint_lines(tool_cfg: dict | None) -> list[str]:
    """Generate recall-reminder hints for the system prompt."""
    task_hint = "- task: list" if not tool_cfg else "- task({ 'operation': 'list' })"
    actor_hint = "- actor: status <actor_id>" if not tool_cfg else "- actor({ 'operation': 'status', 'actor_id': '<id>' })"
    return [
        "- memory: search <keyword>",
        task_hint,
        actor_hint,
    ]


def has_substantive_content(parts: list[dict]) -> bool:
    """Check if message parts carry substantive content."""
    for p in parts:
        ptype = p.get("type", "")
        if ptype in ("text", "file", "subtask", "agent", "tool"):
            text = p.get("text", "")
            if ptype == "text" and text.strip():
                return True
            if ptype == "file":
                return True
            if ptype in ("subtask", "agent"):
                return True
    return False


# ── PromptLoopService ────────────────────────────────────────────────


class PromptLoopService:
    """Main session prompt loop — ported from prompt.ts Service.

    Orchestrates the full session lifecycle:
    - Creating user messages
    - Running the main loop (runLoop)
    - Resolving tools
    - Handling subtasks
    - Shell command execution
    """

    def __init__(self):
        self._sessions = sessions
        self._agents = None
        self._provider = None
        self._processor = processor_service
        self._llm = llm_service
        self._config = None
        self._permission = None
        self._plugin = None
        self._status = session_status
        self._goal = goal_manager
        self._summary = None
        self._checkpoint = None
        self._prune = None
        self._compaction = None
        self._revert = None
        self._instruction = None
        self._registry = None
        self._state = None
        self._mcp = None
        self._sys_prompt = None
        self._actor_registry = None

    def initialize(
        self,
        agents_service=None,
        provider_service=None,
        config_service=None,
        permission_service=None,
        plugin_service=None,
        summary_service=None,
        checkpoint_service=None,
        prune_service=None,
        compaction_service=None,
        revert_service=None,
        instruction_service=None,
        registry_service=None,
        state_service=None,
        mcp_service=None,
        sys_prompt_service=None,
        actor_registry_service=None,
    ) -> None:
        """Initialize with all service dependencies."""
        self._agents = agents_service
        self._provider = provider_service
        self._config = config_service
        self._permission = permission_service
        self._plugin = plugin_service
        self._summary = summary_service
        self._checkpoint = checkpoint_service
        self._prune = prune_service
        self._compaction = compaction_service
        self._revert = revert_service
        self._instruction = instruction_service
        self._registry = registry_service
        self._state = state_service
        self._mcp = mcp_service
        self._sys_prompt = sys_prompt_service
        self._actor_registry = actor_registry_service

    # ── Prompt: top-level entry point ────────────────────────────────

    def prompt(
        self,
        session_id: str,
        parts: list[dict],
        agent: str = "build",
        model: dict | None = None,
        model_ref: str | None = None,
        message_id: str | None = None,
        agent_id: str | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        format: dict | None = None,
        provenance: dict | None = None,
        variant: str | None = None,
        no_reply: bool = False,
        source: str = "user",
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a user message and start the loop.

        Mirrors prompt.ts prompt() function.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Cleanup revert on user-initiated prompts
        if source not in ("spawn", "hook"):
            if self._revert:
                self._revert.cleanup(session_id)

        # Create user message
        user_msg = self._create_user_message(
            session_id=session_id,
            parts=parts,
            agent=agent,
            model=model,
            model_ref=model_ref,
            message_id=message_id,
            agent_id=agent_id,
            system=system,
            tools=tools,
            format=format,
            provenance=provenance,
            variant=variant,
        )

        if not user_msg or not user_msg.get("parts"):
            return user_msg or {"info": {}, "parts": []}

        # Store the user message
        info = user_msg.get("info", {})
        msg_parts = user_msg.get("parts", [])
        if info.get("id"):
            if self._sessions:
                self._sessions._save()

        if no_reply:
            return user_msg

        # Run the loop
        return self.loop(session_id=session_id, agent_id=agent_id or "main", task_id=task_id)

    # ── Loop: main entry point state-managed ─────────────────────────

    def loop(
        self,
        session_id: str,
        agent_id: str = "main",
        task_id: str | None = None,
        notify_parent_on_complete: bool = False,
    ) -> dict[str, Any]:
        """Run the main loop — mirrors prompt.ts loop().

        Checks run state, then delegates to runLoop.
        """
        if self._state:
            try:
                self._state.assert_not_busy(session_id)
            except Exception:
                raise RuntimeError(f"Session {session_id} is busy")

        if self._state:
            runner = self._state.set_busy(session_id, agent_id)

        try:
            result = self._run_loop(
                session_id=session_id,
                agent_id=agent_id,
                task_id=task_id,
                notify_parent_on_complete=notify_parent_on_complete,
            )
            return result
        finally:
            if self._state:
                self._state.set_idle(session_id, agent_id)

    # ── runLoop: the core while loop ─────────────────────────────────

    def _run_loop(
        self,
        session_id: str,
        agent_id: str | None = None,
        task_id: str | None = None,
        notify_parent_on_complete: bool = False,
    ) -> dict[str, Any]:
        """Main run loop — mirrors prompt.ts runLoop.

        The core session orchestration: while True, build messages,
        classify state, resolve tools, stream LLM, handle results.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        resolved_agent_id = agent_id or "main"

        # Loop local state
        step = 0
        structured: Any = None
        last_finished_for_prune: dict | None = None
        last_model_for_prune: dict | None = None
        output_length_continuations = 0
        invalid_continuations = 0
        structured_retries = 0
        text_tool_call_retries = 0
        empty_step_streak = 0
        hard_halt = False
        cancelled = False
        cancel_reason: str | None = None
        last_system_prompt: list[str] | None = None
        skip_overflow_check = False
        text_loop_buffer: list[str] = []
        text_loop_recovery_attempts = 0
        text_ngram_recovery_attempts = 0
        instructions_notified: set[str] = set()
        agent_metrics = {"tokens_in": 0, "tokens_out": 0, "files_changed": 0}

        while True:
            # Set busy status
            if not agent_id or agent_id == "main":
                from craft.core.session.status import StatusBusy
                self._status.set(session_id, StatusBusy())

            step += 1

            # ── 1. Get filtered messages ──
            msgs = self._get_messages(session_id, agent_id or "main")

            # ── 2. Find last user and last finished assistant ──
            last_user: dict | None = None
            last_assistant: dict | None = None
            last_finished: dict | None = None
            tasks: list[dict] = []
            for i in range(len(msgs) - 1, -1, -1):
                msg = msgs[i]
                info = msg.get("info", msg)
                if not last_user and info.get("role") == "user":
                    last_user = info
                if not last_assistant and info.get("role") == "assistant":
                    last_assistant = info
                if not last_finished and info.get("role") == "assistant" and info.get("finish"):
                    last_finished = info
                if last_user and last_finished:
                    break
                task_parts = [p for p in msg.get("parts", []) if p.get("type") == "subtask"]
                if task_parts and not last_finished:
                    tasks.extend(task_parts)

            if not last_user:
                raise ValueError("No user message found in stream.")

            self._inject_memory_recall(msgs, last_user, session_id)
            self._inject_context_pressure_nudge(msgs, last_finished, session_id)
            self._inject_repeated_step_nudge(msgs, last_finished)

            # ── 3. Handle existing assistant classification ──
            if last_assistant:
                last_assistant_msg = None
                for m in reversed(msgs):
                    info = m.get("info", m)
                    if info.get("role") == "assistant" and info.get("id") == last_assistant.get("id"):
                        last_assistant_msg = m
                        break
                parts = last_assistant_msg.get("parts", []) if last_assistant_msg else []

                has_tool_calls = any(
                    p.get("type") == "tool" and not p.get("metadata", {}).get("providerExecuted")
                    for p in parts
                )

                # Output length continuation
                if (
                    last_assistant.get("finish") == "length"
                    and not has_tool_calls
                    and last_user.get("id", "") < last_assistant.get("id", "")
                ):
                    if self._auto_continue_output_length(last_user, last_assistant, output_length_continuations, session_id):
                        output_length_continuations += 1
                        continue

                classification = classify_assistant_step(
                    last_user=last_user,
                    assistant=last_assistant,
                    parts=parts,
                    phase="existing-assistant",
                )
                cls_type = classification.get("type", "")

                if cls_type == "filtered":
                    break
                if cls_type == "failed":
                    break
                if cls_type == "text-tool-call":
                    if text_tool_call_retries < TEXT_TOOL_CALL_RETRY_LIMIT:
                        text_tool_call_retries += 1
                        continue
                    break
                if cls_type in ("think-only", "invalid"):
                    reason = classification.get("reason", "think-only") if cls_type == "invalid" else "think-only"
                    if invalid_continuations < INVALID_OUTPUT_CONTINUATION_LIMIT:
                        invalid_continuations += 1
                        continue
                    break
                if cls_type != "continue":
                    if self._goal_gate(last_user, session_id):
                        continue
                    break

            # ── 4. Resolve model ──
            model = self._resolve_model(last_user)

            # ── 5. Handle tasks/subtasks ──
            if tasks and tasks[-1].get("type") == "subtask":
                self._handle_subtask(tasks[-1], model, last_user, session_id, session, msgs)
                continue

            # ── 6. Handle compaction ──
            last_user_msg = None
            for m in reversed(msgs):
                info = m.get("info", m)
                if info.get("role") == "user":
                    last_user_msg = m
                    break
            if last_user_msg:
                has_compaction = any(p.get("type") == "compaction" for p in last_user_msg.get("parts", []))
                if has_compaction and self._compaction:
                    result = self._compaction.process(
                        parent_id=last_user.get("id", ""),
                        messages=msgs,
                        session_id=session_id,
                        auto=True,
                        agent_id=last_user.get("agentID"),
                    )
                    if result == "stop":
                        break
                    continue

            # ── 7. Context pressure nudge ──
            if last_finished and last_finished.get("summary") is not True:
                from craft.core.session.overflow import pressure_level
                cfg = self._config.get() if self._config else {}
                pressure = pressure_level(cfg, last_finished.get("tokens", {}), model)
                if pressure >= 2:
                    NUDGE_MARKER = "Context is filling up"
                    boundary_id = None
                    if self._checkpoint:
                        boundary_id = self._checkpoint.last_boundary(session_id)
                    already_nudged = nudged_since_boundary(msgs, boundary_id, NUDGE_MARKER)
                    lu_msg = self._find_last_user_msg(msgs)
                    if lu_msg and not already_nudged:
                        lu_msg.setdefault("parts", []).append({
                            "id": PartID.ascending(),
                            "messageID": lu_msg.get("info", lu_msg).get("id", ""),
                            "sessionID": session_id,
                            "type": "text",
                            "synthetic": True,
                            "text": (
                                "<system-reminder>\n"
                                f"Context is filling up ({'>85%' if pressure >= 3 else '>70%'}).\n"
                                "If you have important learnings or decisions from this session that are\n"
                                "not yet in memory, write them now (they may be summarized on the next\n"
                                "checkpoint). This is a save-your-work reminder only.\n"
                                "IMPORTANT: After writing to memory, CONTINUE with the current task in the\n"
                                "same turn. Do NOT stop, wrap up, or hand control back to the user because\n"
                                "of this reminder — only finish when the actual work is done.\n"
                                "</system-reminder>"
                            ),
                        })

            # ── 8. Repeated step nudge ──
            if last_finished:
                recent_sigs: list[str] = []
                for i in range(len(msgs) - 1, -1, -1):
                    if len(recent_sigs) >= REPEATED_STEP_THRESHOLD:
                        break
                    m = msgs[i]
                    info = m.get("info", m)
                    if info.get("role") != "assistant" or not info.get("finish"):
                        continue
                    sig = step_signature(m.get("parts", []))
                    if sig is None:
                        break
                    recent_sigs.append(sig)
                repeating = (
                    len(recent_sigs) == REPEATED_STEP_THRESHOLD
                    and all(s == recent_sigs[0] for s in recent_sigs)
                )
                if repeating:
                    lu_msg = self._find_last_user_msg(msgs)
                    if lu_msg:
                        has_nudge = any(
                            p.get("type") == "text" and "repeating the same action" in p.get("text", "")
                            for p in lu_msg.get("parts", [])
                        )
                        if not has_nudge:
                            lu_msg.setdefault("parts", []).append({
                                "id": PartID.ascending(),
                                "messageID": lu_msg.get("info", lu_msg).get("id", ""),
                                "sessionID": session_id,
                                "type": "text",
                                "synthetic": True,
                                "text": (
                                    "<system-reminder>\n"
                                    f"Your last {REPEATED_STEP_THRESHOLD} steps have been identical — you appear to be\n"
                                    "repeating the same action without making progress. Stop and reconsider:\n"
                                    "the current approach is not working. Try a different strategy, use a\n"
                                    "different tool, or if you are blocked, explain the blocker to the user\n"
                                    "instead of repeating the same step again.\n"
                                    "</system-reminder>"
                                ),
                            })

            # ── 9. Fire background checkpoints ──
            if (
                not skip_overflow_check
                and last_finished
                and last_finished.get("tokens")
                and self._prune
            ):
                self._prune.fire_checkpoints(
                    session_id=session_id,
                    model=model,
                    tokens=last_finished.get("tokens", {}),
                )

            # ── 10. Overflow check ──
            if (
                not skip_overflow_check
                and last_finished
                and last_finished.get("summary") is not True
            ):
                from craft.core.session.overflow import is_overflow
                cfg = self._config.get() if self._config else {}
                if is_overflow(cfg, last_finished.get("tokens", {}), model):
                    if self._compaction:
                        self._compaction.create(
                            session_id=session_id,
                            agent=last_user.get("agent", "build"),
                            model={"providerID": model.get("providerID", ""), "modelID": model.get("id", "")},
                            auto=True,
                            agent_id=last_user.get("agentID"),
                        )
                    skip_overflow_check = True
                    continue
            skip_overflow_check = False

            # ── 11. Create assistant message and process ──
            assistant_msg: dict[str, Any] = {
                "id": MessageID.ascending(),
                "parentID": last_user.get("id", ""),
                "role": "assistant",
                "sessionID": session_id,
                "agentID": last_user.get("agentID"),
                "mode": last_user.get("agent", "build"),
                "agent": last_user.get("agent", "build"),
                "variant": last_user.get("model", {}).get("variant"),
                "cost": 0,
                "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
                "modelID": model.get("id", ""),
                "providerID": model.get("providerID", ""),
                "time": {"created": time.time() * 1000},
                "path": {"cwd": os.getcwd(), "root": os.getcwd()},
            }

            # Create processor handle
            handle = self._processor.create(
                assistant_message=assistant_msg,
                session_id=session_id,
                model=model,
            )

            # Resolve tools
            tools = self._resolve_tools(
                agent={"name": last_user.get("agent", "build")},
                model=model,
                session=session,
                tools=last_user.get("tools"),
                messages=msgs,
            )

            # Process - yield LLM call
            result = self._process_step(
                handle=handle,
                stream_input={
                    "user": last_user,
                    "agent": {"name": last_user.get("agent", "build")},
                    "sessionID": session_id,
                    "system": [],
                    "messages": msgs,
                    "tools": tools,
                    "model": model,
                    "agentID": last_user.get("agentID"),
                },
            )

            # ── 12. Handle step result ──
            if result == ProcessorResult.CONTINUE:
                if self._auto_continue_output_length(last_user, assistant_msg, output_length_continuations, session_id):
                    output_length_continuations += 1
                    continue

            if result == ProcessorResult.TEXT_REPEAT:
                if text_ngram_recovery_attempts >= TEXT_NGRAM_MAX_RECOVERY:
                    break
                recovery_text = TEXT_NGRAM_RECOVERY_REMIND if text_ngram_recovery_attempts == 0 else TEXT_NGRAM_RECOVERY_REPLAN
                self._inject_recovery_message(last_user, session_id, recovery_text)
                text_ngram_recovery_attempts += 1
                continue

            if result == ProcessorResult.STOP:
                break

            if result == ProcessorResult.OVERFLOW:
                if self._compaction:
                    self._compaction.create(
                        session_id=session_id,
                        agent=last_user.get("agent", "build"),
                        model={"providerID": model.get("providerID", ""), "modelID": model.get("id", "")},
                        auto=True,
                        overflow=True,
                        agent_id=last_user.get("agentID"),
                    )
                continue

            # ── 13. Handle empty step ──
            h_es = self._handle_empty_step(last_user, assistant_msg, empty_step_streak, session_id)
            if h_es == "halt":
                hard_halt = True
                break
            if h_es == "continue":
                empty_step_streak += 1
                continue
            # h_es == "none" — reset streak
            empty_step_streak = 0

            # ── 14. Classify step ──
            final_parts = []  # would come from message store
            classification = classify_assistant_step(
                last_user=last_user,
                assistant=assistant_msg,
                parts=final_parts,
                phase="after-process",
                process_result=result,
            )
            cls_type = classification.get("type", "")

            if cls_type == "filtered":
                break
            if cls_type == "failed":
                break
            if cls_type == "text-tool-call":
                if text_tool_call_retries < TEXT_TOOL_CALL_RETRY_LIMIT:
                    text_tool_call_retries += 1
                    continue
                break
            if cls_type in ("think-only", "invalid"):
                reason = classification.get("reason", "think-only") if cls_type == "invalid" else "think-only"
                if invalid_continuations < INVALID_OUTPUT_CONTINUATION_LIMIT:
                    invalid_continuations += 1
                    continue
                break

            # ── 15. Text loop detection (cross-step) ──
            step_text = ""
            for p in final_parts:
                if p.get("type") == "text" and not p.get("synthetic"):
                    step_text += " " + p.get("text", "")
            if step_text.strip():
                tool_sig = "|".join(
                    f'{p.get("tool", "")}:{stable_stringify(p.get("state", {}).get("input", {}))}'
                    for p in final_parts
                    if p.get("type") == "tool"
                )
                normalized = normalize_for_loop_detection(step_text)
                if tool_sig:
                    normalized += "\0" + tool_sig
                text_loop_buffer.append(normalized)
                if len(text_loop_buffer) > TEXT_LOOP_BUFFER_SIZE:
                    text_loop_buffer.pop(0)
                if len(text_loop_buffer) >= TEXT_LOOP_TRIGGER_COUNT:
                    if detect_text_loop(text_loop_buffer, TEXT_LOOP_TRIGGER_COUNT):
                        if text_loop_recovery_attempts >= TEXT_LOOP_MAX_RECOVERY:
                            break
                        recovery = RECOVERY_PROMPT_MILD if text_loop_recovery_attempts == 0 else RECOVERY_PROMPT_STRONG
                        self._inject_recovery_message(last_user, session_id, recovery)
                        text_loop_recovery_attempts += 1
                        text_loop_buffer.clear()
                        continue

            # ── 16. Post-loop checks ──
            if hard_halt:
                break

            if self._goal_gate(last_user, session_id):
                continue

            break  # normal exit

        # Final: return the last assistant message
        return self._get_last_assistant(session_id, agent_id)

    # ── Helper Methods ────────────────────────────────────────────────

    def _create_user_message(
        self,
        session_id: str,
        parts: list[dict],
        agent: str = "build",
        model: dict | None = None,
        model_ref: str | None = None,
        message_id: str | None = None,
        agent_id: str | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        format: dict | None = None,
        provenance: dict | None = None,
        variant: str | None = None,
    ) -> dict[str, Any]:
        """Create and store a user message — mirrors createUserMessage in prompt.ts."""
        from craft.core.session._session import Session

        # Resolve agent
        if self._agents:
            # In a full implementation, look up the agent
            pass

        # Resolve model
        resolved_model = model or {"providerID": "", "modelID": ""}

        # Create user info
        info: dict[str, Any] = {
            "id": message_id or MessageID.ascending(),
            "role": "user",
            "sessionID": session_id,
            "agentID": agent_id,
            "time": {"created": time.time() * 1000},
            "tools": tools,
            "agent": agent,
            "model": {
                "providerID": resolved_model.get("providerID", ""),
                "modelID": resolved_model.get("modelID", ""),
                "variant": variant,
            },
            "system": system,
            "format": format,
            "provenance": provenance,
        }

        # Resolve parts (assign IDs)
        resolved_parts: list[dict] = []
        for p in parts:
            resolved = dict(p)
            resolved.setdefault("id", PartID.ascending())
            resolved.setdefault("messageID", info["id"])
            resolved.setdefault("sessionID", session_id)
            resolved_parts.append(resolved)

        # Guard: reject empty content
        if not has_substantive_content(resolved_parts):
            return {"info": info, "parts": []}

        # Persist to session
        session_obj = self._sessions.get(session_id)
        if session_obj and hasattr(session_obj, "add_message"):
            msg_record = {
                "id": info["id"],
                "role": "user",
                "agent": agent,
                "time": info["time"],
                "model": info["model"],
                "parts": resolved_parts,
            }
            # Use add_message but avoid double-appending
            session_obj.messages.append(msg_record)
            session_obj.updated_at = time.time()

        # In a full implementation, persist to DB
        return {"info": info, "parts": resolved_parts}

    def _get_messages(self, session_id: str, agent_id: str) -> list[dict]:
        """Get filtered messages for the session context window."""
        session_data = self._sessions.get(session_id)
        if session_data:
            raw = getattr(session_data, "messages", [])
            result = []
            for m in raw:
                if isinstance(m, dict):
                    if "info" in m or "role" in m:
                        result.append(m if "info" in m else {"info": m, "parts": m.get("parts", [])})
                    elif "role" in m:
                        result.append({"info": m, "parts": m.get("parts", [])})
                    else:
                        result.append({"info": m, "parts": []})
            return result
        return []

    def _resolve_model(self, last_user: dict) -> dict[str, Any]:
        """Resolve the model from user info."""
        user_model = last_user.get("model", {})
        return {
            "id": user_model.get("modelID", ""),
            "providerID": user_model.get("providerID", ""),
        }

    def _resolve_tools(
        self,
        agent: dict,
        model: dict,
        session: Any,
        tools: dict[str, bool] | None,
        messages: list[dict],
    ) -> dict[str, Any]:
        """Resolve tools for the current step — mirrors resolveTools in prompt.ts."""
        # In a full implementation, this would load tools from the registry
        return {}

    def _process_step(
        self,
        handle: ProcessorHandle,
        stream_input: dict,
    ) -> str:
        """Process a single LLM step."""
        return handle.process(stream_input)

    def _inject_memory_recall(self, msgs: list[dict], last_user: dict, session_id: str) -> None:
        """Inject memory recall hints if the session has memory targets."""
        # In a full implementation, check checkpoint.hasMemoryOrTasks
        pass

    def _inject_context_pressure_nudge(self, msgs: list[dict], last_finished: dict | None, session_id: str) -> None:
        """Inject context pressure nudge if applicable."""
        pass

    def _inject_repeated_step_nudge(self, msgs: list[dict], last_finished: dict | None) -> None:
        """Inject repeated-step nudge if applicable."""
        pass

    def _inject_recovery_message(self, last_user: dict, session_id: str, recovery_text: str) -> None:
        """Inject a recovery message as a new synthetic user turn."""
        # In a full implementation, create a new user message with the recovery text

    def _find_last_user_msg(self, msgs: list[dict]) -> dict | None:
        """Find the last user message in the list."""
        for m in reversed(msgs):
            info = m.get("info", m)
            if info.get("role") == "user":
                return m
        return None

    def _handle_subtask(
        self,
        task: dict,
        model: dict,
        last_user: dict,
        session_id: str,
        session: Any,
        msgs: list[dict],
    ) -> None:
        """Handle a subtask — mirrors handleSubtask in prompt.ts."""
        # In a full implementation, create an actor tool call
        pass

    def _handle_empty_step(
        self,
        last_user: dict,
        assistant: dict,
        empty_step_streak: int,
        session_id: str,
    ) -> str:
        """Handle empty/no-op tool-call loop guard.

        Returns "none" (not empty, continue normal), "continue" (recovery injected),
        or "halt" (max recovery exceeded).
        """
        if (
            assistant.get("error")
            or assistant.get("summary")
            or assistant.get("structured") is not None
            or assistant.get("finish") in ("content-filter", "error")
        ):
            return "none"

        parts = []  # In a full implementation, load parts
        if not is_empty_step(parts):
            return "none"

        if empty_step_streak >= EMPTY_STEP_MAX_RECOVERY:
            return "halt"

        recovery = EMPTY_STEP_RECOVERY_REMIND if empty_step_streak == 0 else EMPTY_STEP_RECOVERY_REPLAN
        self._inject_recovery_message(last_user, session_id, recovery)
        return "continue"

    def _auto_continue_output_length(
        self,
        last_user: dict,
        assistant: dict,
        continuations: int,
        session_id: str,
    ) -> bool:
        """Auto-continue on output length limit."""
        if (
            assistant.get("finish") != "length"
            or assistant.get("error")
            or assistant.get("summary")
        ):
            return False
        if continuations >= OUTPUT_LENGTH_CONTINUATION_LIMIT:
            return False
        # In a full implementation, create a continuation user message
        return True

    def _goal_gate(self, last_user: dict, session_id: str) -> bool:
        """Goal stop-condition gate. Returns True if ReAct re-entry is needed."""
        active = self._goal.get(session_id)
        if not active:
            return False
        if session_id and session_id.startswith("ses_") and last_user.get("agentID"):
            # Non-main agents skip goal gate
            if last_user.get("agentID") != "main":
                return False
        return False  # In a full implementation, would check with a judge model

    def _get_last_assistant(self, session_id: str, agent_id: str | None) -> dict[str, Any]:
        """Get the last assistant message."""
        session_data = self._sessions.get(session_id)
        if session_data:
            msgs = getattr(session_data, "messages", [])
            for m in reversed(msgs):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    return m
        return {"id": "", "role": "assistant", "parts": []}


# ── Global Instance ───────────────────────────────────────────────────

prompt_loop_service = PromptLoopService()
