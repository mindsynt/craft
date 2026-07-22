"""Tool attachment routing — ported from tool-attachment.ts.

Determines how a tool attachment should be sent to a model based on
the model's capabilities and provider.
"""

from __future__ import annotations

import re
from typing import Any, Literal

SAFE_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
OPENAI_AUDIO_MIMES = {"audio/wav", "audio/mp3", "audio/mpeg"}
BEDROCK_TEXT_MIMES = {"text/csv", "text/html", "text/plain", "text/markdown"}
OPENAI_CHAT_PACKAGES = {"@ai-sdk/openai-compatible"}
ANTHROPIC_PACKAGES = {"@ai-sdk/anthropic", "@ai-sdk/google-vertex/anthropic"}
GOOGLE_PACKAGES = {"@ai-sdk/google", "@ai-sdk/google-vertex"}
MAX_ATTACHMENT_NAME_LENGTH = 120

ToolAttachmentRoute = Literal["native", "synthetic", "placeholder"]


def is_inline_attachment(attachment: dict[str, Any]) -> bool:
    return inline_tool_attachment(attachment) is not None


def is_remote_url(url: str) -> bool:
    return bool(re.match(r"^https?://", url, re.IGNORECASE))


def model_accepts_mime(model: dict[str, Any], mime: str) -> bool:
    caps = model.get("capabilities", {}).get("input", {})
    if mime.startswith("image/"):
        return mime in SAFE_IMAGE_MIMES and caps.get("image", False)
    if mime == "application/pdf":
        return caps.get("pdf", False)
    if mime.startswith("audio/"):
        return caps.get("audio", False)
    if mime.startswith("video/"):
        return caps.get("video", False)
    if mime.startswith("text/"):
        return caps.get("text", True)
    return False


def _sanitize_url_name(s: str) -> str:
    """Extract a bounded filename from a URL or path."""
    if re.match(r"^data:", s, re.IGNORECASE):
        mime_part = s[5:].split(";", 1)[0].split(",", 1)[0]
        clean = re.sub(r"[^a-z0-9.+/-]", "", mime_part)[:80]
        return f"data URI ({clean})" if clean else "data URI"
    name = s.split("/")[-1] if "/" in s else s
    name = name.split("?")[0].split("#")[0] if name else s
    clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", name).replace('"', "'")
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return "attachment"
    if len(clean) <= MAX_ATTACHMENT_NAME_LENGTH:
        return clean
    return clean[: MAX_ATTACHMENT_NAME_LENGTH - 3] + "..."


def route_tool_attachment(
    model: dict[str, Any],
    attachment: dict[str, Any],
    allow_native: bool = True,
) -> ToolAttachmentRoute:
    """Determine how to route a tool attachment to a model."""
    if not model_accepts_mime(model, attachment.get("mime", "")):
        return "placeholder"
    if allow_native and _provider_accepts_native(model, attachment):
        return "native"
    if _provider_accepts_synthetic(model, attachment):
        return "synthetic"
    return "placeholder"


def inline_tool_attachment(attachment: dict[str, Any]) -> dict | None:
    """Check if attachment is a data URI and return decoded info."""
    url = attachment.get("url", "")
    m = re.match(r"^data:([^;,]+);base64,([a-z0-9+/]+={0,2})$", url, re.IGNORECASE)
    if not m:
        return None
    if m.group(1).lower() != attachment.get("mime", "").lower():
        return None
    return {"data": m.group(2), "mediaType": attachment["mime"]}


def tool_attachment_filename(attachment: dict[str, Any]) -> str | None:
    """Get a safe filename for a tool attachment."""
    filename = attachment.get("filename")
    if not filename or re.match(r"^data:", str(filename).strip(), re.IGNORECASE):
        return None
    safe = _sanitize_url_name(filename)
    safe = re.sub(r"[^a-z0-9 .()\-]", "-", safe)
    safe = re.sub(r"-+", "-", safe)
    safe = re.sub(r"^[ .-]+|[ .-]+$", "", safe)
    return safe or None


def tool_attachment_placeholder(attachment: dict[str, Any]) -> str:
    """Generate a placeholder string for an attachment that can't be sent."""
    filename = attachment.get("filename")
    name = f'"{_sanitize_url_name(filename)}"' if filename else "an unnamed attachment"
    mime = re.sub(r"[^a-z0-9.+/-]", "", attachment.get("mime", ""))[:80] or "unknown"
    return f"[Tool attachment {name} ({mime}) was retained but cannot be safely sent to this model/provider.]"


def _is_gemini3(model: dict[str, Any]) -> bool:
    api_id = model.get("api", {}).get("id", "")
    return api_id.startswith("gemini-3")


def _provider_accepts_synthetic(model: dict[str, Any], attachment: dict[str, Any]) -> bool:
    npm = model.get("api", {}).get("npm", "")
    mime = attachment.get("mime", "")

    if mime in SAFE_IMAGE_MIMES:
        return is_inline_attachment(attachment) or is_remote_url(attachment.get("url", ""))
    if mime == "application/pdf":
        return is_inline_attachment(attachment)
    if mime.startswith("audio/"):
        if not is_inline_attachment(attachment):
            return False
        if npm in OPENAI_CHAT_PACKAGES:
            return mime in OPENAI_AUDIO_MIMES
        return npm in GOOGLE_PACKAGES
    if mime.startswith("video/"):
        return is_inline_attachment(attachment) and npm in GOOGLE_PACKAGES
    if mime.startswith("text/"):
        if not is_inline_attachment(attachment):
            return False
        if npm in OPENAI_CHAT_PACKAGES or npm in GOOGLE_PACKAGES:
            return True
        if npm == "@ai-sdk/amazon-bedrock":
            return mime in BEDROCK_TEXT_MIMES
        return npm in ANTHROPIC_PACKAGES and mime == "text/plain"
    return False


def _provider_accepts_native(model: dict[str, Any], attachment: dict[str, Any]) -> bool:
    if not is_inline_attachment(attachment):
        return False
    npm = model.get("api", {}).get("npm", "")
    mime = attachment.get("mime", "")

    if npm in ANTHROPIC_PACKAGES or npm == "@ai-sdk/amazon-bedrock":
        return mime in SAFE_IMAGE_MIMES or mime == "application/pdf"
    if npm in GOOGLE_PACKAGES and _is_gemini3(model):
        return (
            mime in SAFE_IMAGE_MIMES
            or mime == "application/pdf"
            or mime.startswith("audio/")
            or mime.startswith("video/")
        )
    return False
