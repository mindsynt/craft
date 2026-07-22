"""Step classification — ported from classify.ts.

Single source of truth for 'is this assistant step terminal, or should the
loop keep going?'
"""

from __future__ import annotations

from typing import Any, Literal


StepClassification = (
    dict[Literal["type"], Literal["final"]]
    | dict[Literal["type", "degraded"], Literal["final"] | bool]
    | dict[Literal["type"], Literal["continue"]]
    | dict[Literal["type"], Literal["text-tool-call"]]
    | dict[Literal["type"], Literal["filtered"]]
    | dict[Literal["type"], Literal["think-only"]]
    | dict[Literal["type", "reason"], Literal["invalid"] | str]
    | dict[Literal["type", "reason"], Literal["failed"] | str]
)


def classify_assistant_step(
    last_user: dict[str, Any],
    assistant: dict[str, Any],
    parts: list[dict[str, Any]],
    phase: str = "after-process",
    process_result: str | None = None,
) -> dict[str, Any]:
    """Classify whether an assistant step is terminal or should continue."""

    # 1. Core guarantee — pending client tool call must re-loop
    for part in parts:
        if (
            part.get("type") == "tool"
            and not part.get("metadata", {}).get("providerExecuted")
            and part.get("state", {}).get("status") != "error"
        ):
            return {"type": "continue"}

    # 2. Nothing finalized yet
    if not assistant.get("finish"):
        return {"type": "continue"}

    # 3a. Text-form tool call
    if (
        assistant.get("finish") == "tool-calls"
        and not assistant.get("error")
        and last_user.get("id", "") < assistant.get("id", "")
        and not any(p.get("type") == "tool" for p in parts)
        and any(
            p.get("type") == "text"
            and not p.get("synthetic")
            and not p.get("ignored")
            and "<invoke name=" in p.get("text", "")
            for p in parts
        )
    ):
        return {"type": "text-tool-call"}

    # 3. Provider-executed-only tool step
    if assistant.get("finish") == "tool-calls":
        return {"type": "continue"}

    # 4. Stale assistant
    if phase == "existing-assistant" and not (last_user.get("id", "") < assistant.get("id", "")):
        return {"type": "continue"}

    # 5. Errored step
    if assistant.get("error"):
        return {"type": "failed", "reason": assistant["error"].get("name", "unknown")}

    # 6. Already-resolved structured output / summary
    if assistant.get("structured") is not None:
        return {"type": "final"}
    if assistant.get("summary"):
        return {"type": "final"}

    # 7. Safety / error finish reasons
    if assistant.get("finish") == "content-filter":
        return {"type": "filtered"}
    if assistant.get("finish") == "error":
        return {"type": "failed", "reason": "model error finish"}

    # 8. stop / length / other → inspect content
    has_text = any(
        p.get("type") == "text"
        and not p.get("synthetic")
        and not p.get("ignored")
        and p.get("text", "").strip()
        for p in parts
    )
    if has_text:
        degraded = assistant.get("finish") == "other"
        r: dict[str, Any] = {"type": "final"}
        if degraded:
            r["degraded"] = True
        return r

    has_reasoning = any(
        p.get("type") == "reasoning" and p.get("text", "").strip()
        for p in parts
    )
    if has_reasoning:
        model_id = assistant.get("model_id", "")
        if "gpt-" in model_id.split("/")[-1] if "/" in model_id else model_id.lower().startswith("gpt-"):
            degraded = assistant.get("finish") == "other"
            r: dict[str, Any] = {"type": "final"}
            if degraded:
                r["degraded"] = True
            return r
        return {"type": "think-only"}

    return {"type": "invalid", "reason": "empty output"}
