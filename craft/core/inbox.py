"""
收件箱/通知系统 — 移植自 packages/opencode/src/inbox/
通知管理、消息队列、实时推送
"""

from __future__ import annotations

import json
import time
import uuid

from craft.config import CONFIG_DIR

INBOX_DB = CONFIG_DIR / "inbox.json"


class InboxMessage:
    def __init__(self, type: str = "info", title: str = "", content: str = "",
                 source: str = "system", actionable: bool = False):
        self.id = f"msg_{uuid.uuid4().hex[:12]}"
        self.type = type  # info / success / warning / error
        self.title = title
        self.content = content
        self.source = source
        self.actionable = actionable
        self.read = False
        self.created_at = time.time()

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class Inbox:
    def __init__(self):
        self._messages: list[InboxMessage] = []
        self._load()

    def _load(self):
        try:
            if INBOX_DB.exists():
                data = json.loads(INBOX_DB.read_text())
                for item in data:
                    msg = InboxMessage()
                    msg.__dict__.update(item)
                    self._messages.append(msg)
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        INBOX_DB.write_text(json.dumps(
            [m.to_dict() for m in self._messages], indent=2, default=str
        ))

    def add(self, type: str = "info", title: str = "", content: str = "",
            source: str = "system", actionable: bool = False) -> str:
        msg = InboxMessage(type, title, content, source, actionable)
        self._messages.insert(0, msg)
        self._save()
        return msg.id

    def list(self, unread_only: bool = False, limit: int = 50) -> list[dict]:
        msgs = [m for m in self._messages if not unread_only or not m.read]
        return [m.to_dict() for m in msgs[:limit]]

    def mark_read(self, msg_id: str) -> bool:
        for m in self._messages:
            if m.id == msg_id:
                m.read = True
                self._save()
                return True
        return False

    def mark_all_read(self):
        for m in self._messages:
            m.read = True
        self._save()

    def unread_count(self) -> int:
        return sum(1 for m in self._messages if not m.read)

    def clear(self):
        self._messages.clear()
        self._save()


inbox = Inbox()


# ── 延迟引用 (对应 inbox-ref.ts) ──────────────────────────────

# SessionPromptLoopRef: 由 SessionPrompt 在初始化时填入
session_prompt_loop_ref: dict | None = None
"""延迟引用的会话提示循环器 — 由 SessionPrompt.layer 在初始化时填入"""

# DefaultModelRef: 由 SessionPrompt 在初始化时填入
default_model_ref: dict | None = None
"""延迟引用的默认模型解析器 — 由 SessionPrompt.layer 在初始化时填入"""

# InboxServiceRef: 由 Inbox.layer 在初始化时填入
inbox_service_ref: dict | None = None
"""延迟引用的收件箱服务 — 由 Inbox.layer 在初始化时填入"""


# ── 渲染工具 (对应 render.ts) ─────────────────────────────────


def render_inbox_row(row: dict) -> str:
    """渲染收件箱消息行

    对应 TS renderInboxRow()。
    """
    content: dict = row.get("content", {})
    content_text = content.get("text", "")

    if row.get("type") == "actor_notification":
        return content_text or "(no notification body)"

    sender = row.get("sender_session_id", "")
    if sender:
        sender = f"{sender}:{row.get('sender_actor_id', '?') or '?'}"
    else:
        sender = "system"

    sent_at = str(row.get("created_at", 0))
    text = content_text or "(empty)"
    return f'<inbox from="{sender}" sent_at="{sent_at}">\n{text}\n</inbox>'


def render_actor_notification(event: dict) -> str:
    """渲染 Actor 通知文本

    对应 TS renderActorNotification()。
    """
    actor_id = event.get("actorID", "")
    description = event.get("description", "")
    status = event.get("status", "")
    result = event.get("result")
    error = event.get("error")
    reported_status = event.get("reportedStatus")
    reported_summary = event.get("reportedSummary")
    stalled_for_ms = event.get("stalledForMs")

    header = f'Background sub-session "{description}" (actor_id: {actor_id})'

    if status == "completed":
        reported = (reported_status or "").lower()
        summary_line = f"\nSummary: {reported_summary}" if reported_summary else ""
        result_line = f"\nResult: {result or '(no output)'}"
        if not reported or reported in ("success", "partial"):
            status_line = f"\nStatus: {reported}" if reported else ""
            return (
                f"<actor-notification>\n{header} completed.{status_line}"
                f"{summary_line}{result_line}\n</actor-notification>"
            )
        if reported in ("failed", "blocked"):
            return (
                f"<actor-notification>\n{header} finished (status: {reported})."
                f"{summary_line}{result_line}\n</actor-notification>"
            )
        return (
            f"<actor-notification>\n{header} ended (status not reported)."
            f"{summary_line}{result_line}\n</actor-notification>"
        )
    if status == "failed":
        return (
            f"<actor-notification>\n{header} failed.\nError: {error or 'unknown'}"
            f"\n</actor-notification>"
        )
    if status == "stalled":
        for_line = ""
        if stalled_for_ms is not None:
            for_line = f" (no turn advance for {int(stalled_for_ms / 1000)}s)"
        return (
            f"<actor-notification>\n{header} appears stalled{for_line}."
            f" It is still running but has made no progress."
            f" Consider checking on it, sending it a nudge, or cancelling it."
            f"\n</actor-notification>"
        )
    return f"<actor-notification>\n{header} was cancelled.\n</actor-notification>"


def parse_actor_notification(text: str) -> dict | None:
    """解析 Actor 通知文本为结构化数据

    对应 TS parseActorNotification()。返回包含 status, description, summary 的字典，
    或 None 如果不是 Actor 通知。
    """
    if not text.strip().startswith("<actor-notification>"):
        return None

    import re
    header = re.search(
        r'Background (?:sub-session|actor) "(.*?)" \(actor_id: [^)]*\)\s+'
        r"(completed|finished|ended|failed|was cancelled|stalled)\b",
        text,
    )
    if not header:
        return None

    description = header.group(1)
    verb = header.group(2)

    if verb == "completed":
        status = "completed"
    elif verb in ("finished", "failed"):
        status = "failed"
    elif verb == "ended":
        status = "ended"
    elif verb == "stalled":
        status = "stalled"
    else:
        status = "cancelled"

    result_idx = text.find("\nResult:")
    before_result = text[:result_idx] if result_idx >= 0 else text

    def find_line(label: str, scope: str) -> str | None:
        m = re.search(rf"^{label}:\s*(.+)$", scope, re.MULTILINE)
        return m.group(1).strip() if m else None

    summary = (
        find_line("Summary", before_result)
        or find_line("Result", text)
        or find_line("Error", text)
    )
    if summary:
        return {"status": status, "description": description, "summary": summary}
    return {"status": status, "description": description}
