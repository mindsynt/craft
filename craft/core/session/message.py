"""Message types — ported from message.ts and message-v2.ts (schema subset).

Contains data model definitions for messages, parts, tool states,
and related types used across the session system.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ToolStateStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class PartType(str, Enum):
    TEXT = "text"
    REASONING = "reasoning"
    TOOL = "tool"
    FILE = "file"
    TOOL_INVOCATION = "tool-invocation"
    SOURCE_URL = "source-url"
    STEP_START = "step-start"
    STEP_FINISH = "step-finish"
    SNAPSHOT = "snapshot"
    PATCH = "patch"
    AGENT = "agent"
    RETRY = "retry"
    CHECKPOINT = "checkpoint"
    SUBTASK = "subtask"
    COMPACTION = "compaction"


@dataclass
class TimeRange:
    start: float = 0.0  # unix ms
    end: float | None = None


@dataclass
class CacheTokens:
    read: int = 0
    write: int = 0


@dataclass
class AssistantTokens:
    total: int | None = None
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache: CacheTokens = field(default_factory=CacheTokens)


@dataclass
class AssistantPath:
    cwd: str = ""
    root: str = ""


@dataclass
class AssistantCost:
    cost: float = 0.0


@dataclass
class UserModel:
    provider_id: str = ""
    model_id: str = ""
    variant: str | None = None


@dataclass
class Provenance:
    hook_phase: Literal["pre", "post"] = "pre"
    hook_iteration: int = 0
    plugin_names: list[str] = field(default_factory=list)
    hook_ids: list[str] = field(default_factory=list)


@dataclass
class OutputFormatText:
    type: Literal["text"] = "text"


@dataclass
class OutputFormatJsonSchema:
    type: Literal["json_schema"] = "json_schema"
    schema: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 2


OutputFormat = OutputFormatText | OutputFormatJsonSchema


def _new_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- Parts ---


@dataclass
class PartBase:
    id: str = field(default_factory=lambda: _new_id("part"))
    session_id: str = ""
    message_id: str = ""


@dataclass
class TextPart(PartBase):
    type: Literal["text"] = "text"
    text: str = ""
    synthetic: bool = False
    ignored: bool = False
    time: TimeRange | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningPart(PartBase):
    type: Literal["reasoning"] = "reasoning"
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    time: TimeRange | None = None


@dataclass
class FilePartSource:
    type: str = "file"
    path: str = ""
    text: dict | None = None  # {'value': ..., 'start': ..., 'end': ...}


@dataclass
class FilePart(PartBase):
    type: Literal["file"] = "file"
    mime: str = ""
    filename: str | None = None
    url: str = ""
    source: FilePartSource | None = None


@dataclass
class ToolStateBase:
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolStatePending(ToolStateBase):
    status: Literal["pending"] = "pending"
    raw: str = ""


@dataclass
class ToolStateRunning(ToolStateBase):
    status: Literal["running"] = "running"
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    time: TimeRange = field(default_factory=TimeRange)


@dataclass
class ToolStateCompleted(ToolStateBase):
    status: Literal["completed"] = "completed"
    output: str = ""
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    time: TimeRange = field(default_factory=TimeRange)
    attachments: list[FilePart] = field(default_factory=list)


@dataclass
class ToolStateError(ToolStateBase):
    status: Literal["error"] = "error"
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    time: TimeRange = field(default_factory=TimeRange)
    attachments: list[FilePart] = field(default_factory=list)


ToolState = ToolStatePending | ToolStateRunning | ToolStateCompleted | ToolStateError


@dataclass
class ToolPart(PartBase):
    type: Literal["tool"] = "tool"
    call_id: str = ""
    tool: str = ""
    state: ToolState = field(default_factory=ToolStatePending)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepStartPart(PartBase):
    type: Literal["step-start"] = "step-start"
    snapshot: str | None = None


@dataclass
class StepFinishPart(PartBase):
    type: Literal["step-finish"] = "step-finish"
    reason: str = ""
    snapshot: str | None = None
    cost: float = 0.0
    tokens: AssistantTokens = field(default_factory=lambda: AssistantTokens())


@dataclass
class SnapshotPart(PartBase):
    type: Literal["snapshot"] = "snapshot"
    snapshot: str = ""


@dataclass
class PatchPart(PartBase):
    type: Literal["patch"] = "patch"
    hash: str = ""
    files: list[str] = field(default_factory=list)


@dataclass
class AgentPart(PartBase):
    type: Literal["agent"] = "agent"
    name: str = ""
    source: dict | None = None


@dataclass
class RetryPart(PartBase):
    type: Literal["retry"] = "retry"
    attempt: int = 0
    error: dict[str, Any] = field(default_factory=dict)
    time: TimeRange = field(default_factory=TimeRange)


@dataclass
class CheckpointPart(PartBase):
    type: Literal["checkpoint"] = "checkpoint"
    checkpoint_dir: str = ""
    checkpoint_number: int = 0
    covered_up_to: str = ""


@dataclass
class SubtaskPart(PartBase):
    type: Literal["subtask"] = "subtask"
    prompt: str = ""
    description: str = ""
    agent: str = ""


@dataclass
class CompactionPart(PartBase):
    type: Literal["compaction"] = "compaction"
    auto: bool = False
    overflow: bool | None = None
    tail_start_id: str | None = None


Part = (
    TextPart
    | ReasoningPart
    | ToolPart
    | FilePart
    | StepStartPart
    | StepFinishPart
    | SnapshotPart
    | PatchPart
    | AgentPart
    | RetryPart
    | CheckpointPart
    | SubtaskPart
    | CompactionPart
)


# --- Messages ---


@dataclass
class BaseMessage:
    id: str = field(default_factory=lambda: _new_id("msg"))
    session_id: str = ""
    agent_id: str = ""


@dataclass
class UserMessage(BaseMessage):
    role: Literal["user"] = "user"
    time: TimeRange = field(default_factory=TimeRange)
    format: OutputFormat | None = None
    agent: str = "build"
    model: UserModel = field(default_factory=UserModel)
    system: str | None = None
    tools: dict[str, bool] | None = None
    provenance: Provenance | None = None
    summary: dict | None = None  # {'title'?, 'body'?, 'diffs': [...]}


@dataclass
class AssistantMessage(BaseMessage):
    role: Literal["assistant"] = "assistant"
    time: TimeRange = field(default_factory=TimeRange)
    error: dict | None = None
    parent_id: str = ""
    model_id: str = ""
    provider_id: str = ""
    mode: str = ""
    agent: str = ""
    path: AssistantPath = field(default_factory=AssistantPath)
    summary: bool = False
    cost: float = 0.0
    tokens: AssistantTokens = field(default_factory=lambda: AssistantTokens())
    structured: Any = None
    variant: str | None = None
    finish: str | None = None


Message = UserMessage | AssistantMessage


@dataclass
class MessageWithParts:
    info: Message
    parts: list[Part] = field(default_factory=list)
