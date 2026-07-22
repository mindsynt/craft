"""
MCP 协议 — 移植自 packages/opencode/src/mcp/
Model Context Protocol 服务器管理

支持：OAuth 回调服务器、OAuth 提供商、工具结果标准化
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Tool Result Normalization ─────────────────────────────────
# 对应 TS mcp/tool-result.ts

@dataclass
class ToolResultAttachment:
    """An attachment extracted from an MCP tool result."""
    mime: str = ""
    url: str = ""
    filename: str | None = None


@dataclass
class ToolResultMetadata:
    """Metadata for an MCP tool result."""
    is_error: bool = False
    structured_content: Any = None
    legacy_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedToolResult:
    """A normalized MCP CallToolResult ready for model consumption."""
    content: list[dict] = field(default_factory=list)
    is_error: bool = False
    output: str = ""
    attachments: list[ToolResultAttachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=lambda: {"mcp": {}})


def _contains_serialized_block(output: str, serialized: str) -> bool:
    """Check if serialized content is already present in the output text."""
    value = output.replace("\r\n", "\n").strip()
    return (
        value == serialized
        or value.startswith(f"{serialized}\n")
        or value.endswith(f"\n{serialized}")
        or f"\n{serialized}\n" in value
    )


def normalize_tool_result(result: dict) -> NormalizedToolResult:
    """Convert a raw MCP CallToolResult dict into NormalizedToolResult.

    Extracts text content, images/audio/resources as attachments,
    and preserves structured content and metadata.
    """
    text: list[str] = []
    attachments: list[ToolResultAttachment] = []

    for item in result.get("content", []):
        item_type = item.get("type", "")

        if item_type == "text":
            text.append(item.get("text", ""))
            continue

        if item_type in ("image", "audio"):
            mime = item.get("mimeType", "application/octet-stream")
            data = item.get("data", "")
            attachments.append(ToolResultAttachment(
                mime=mime,
                url=f"data:{mime};base64,{data}",
            ))
            continue

        if item_type == "resource":
            resource = item.get("resource", {})
            if "text" in resource:
                text.append(resource["text"])
            if "blob" in resource:
                mime = resource.get("mimeType", "application/octet-stream")
                attachments.append(ToolResultAttachment(
                    mime=mime,
                    url=f"data:{mime};base64,{resource['blob']}",
                    filename=resource.get("uri", ""),
                ))

    text_output = "\n\n".join(text)
    structured = result.get("structuredContent")

    # Deduplicate structured content if already in text
    already_serialized = False
    if structured is not None:
        serialized = json.dumps(structured)
        pretty = json.dumps(structured, indent=2)
        already_serialized = (
            _contains_serialized_block(text_output, serialized)
            or _contains_serialized_block(text_output, pretty)
        )

    has_visible_text = any(t.strip() for t in text)
    if structured is not None and not already_serialized:
        output = (
            f"{text_output}\n\nStructured content:\n{json.dumps(structured)}"
            if has_visible_text
            else json.dumps(structured)
        )
    else:
        output = text_output

    metadata: ToolResultMetadata = ToolResultMetadata(
        is_error=result.get("isError", False),
        structured_content=structured,
        legacy_metadata=result.get("metadata", {}),
    )

    return NormalizedToolResult(
        content=result.get("content", []),
        is_error=result.get("isError", False),
        output=output,
        attachments=attachments,
        metadata={"mcp": {
            "isError": metadata.is_error,
            "structuredContent": metadata.structured_content,
            "legacyMetadata": metadata.legacy_metadata,
        }},
    )


# ── OAuth Provider ────────────────────────────────────────────
# 对应 TS mcp/oauth-provider.ts

OAUTH_CALLBACK_PORT = 19876
OAUTH_CALLBACK_PATH = "/mcp/oauth/callback"


@dataclass
class OAuthTokens:
    """OAuth token storage."""
    access_token: str = ""
    refresh_token: str | None = None
    expires_at: float | None = None
    scope: str | None = None


@dataclass
class OAuthClientInfo:
    """OAuth client registration information."""
    client_id: str = ""
    client_secret: str | None = None
    client_id_issued_at: float | None = None
    client_secret_expires_at: float | None = None


def parse_redirect_uri(redirect_uri: str | None = None) -> tuple[int, str]:
    """Parse a redirect URI to extract port and path.

    Returns defaults (OAUTH_CALLBACK_PORT, OAUTH_CALLBACK_PATH) if URI is invalid.
    """
    if not redirect_uri:
        return OAUTH_CALLBACK_PORT, OAUTH_CALLBACK_PATH
    try:
        from urllib.parse import urlparse
        parsed = urlparse(redirect_uri)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or OAUTH_CALLBACK_PATH
        return port, path
    except Exception:
        return OAUTH_CALLBACK_PORT, OAUTH_CALLBACK_PATH


# ── OAuth Callback Server ─────────────────────────────────────
# 对应 TS mcp/oauth-callback.ts

_HTML_SUCCESS = """<!DOCTYPE html>
<html>
<head>
  <title>Craft - Authorization Successful</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #1a1a2e; color: #eee; }
    .container { text-align: center; padding: 2rem; }
    h1 { color: #4ade80; margin-bottom: 1rem; }
    p { color: #aaa; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Successful</h1>
    <p>You can close this window and return to Craft.</p>
  </div>
  <script>setTimeout(() => window.close(), 2000);</script>
</body>
</html>"""


def _html_error(error: str) -> str:
    escaped = (error.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace('"', "&quot;")
               .replace("'", "&#39;"))
    return f"""<!DOCTYPE html>
<html>
<head>
  <title>Craft - Authorization Failed</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #1a1a2e; color: #eee; }}
    .container {{ text-align: center; padding: 2rem; }}
    h1 {{ color: #f87171; margin-bottom: 1rem; }}
    p {{ color: #aaa; }}
    .error {{ color: #fca5a5; font-family: monospace; margin-top: 1rem; padding: 1rem; background: rgba(248,113,113,0.1); border-radius: 0.5rem; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Failed</h1>
    <p>An error occurred during authorization.</p>
    <div class="error">{escaped}</div>
  </div>
</body>
</html>"""


_CALLBACK_TIMEOUT_MS = 5 * 60  # 5 minutes
_pending_auths: dict[str, dict[str, Any]] = {}
_mcp_name_to_state: dict[str, str] = {}
_callback_server: Any = None
_current_port = OAUTH_CALLBACK_PORT
_current_path = OAUTH_CALLBACK_PATH


async def _handle_callback(
    code: str | None,
    state: str | None,
    error: str | None,
    error_description: str | None,
) -> tuple[int, str, str | None]:
    """Handle an OAuth callback request. Returns (status_code, html_body, auth_code)."""
    if not state:
        return 400, _html_error("Missing required state parameter - potential CSRF attack"), None

    if error:
        error_msg = error_description or error
        if state in _pending_auths:
            pending = _pending_auths.pop(state)
            _cleanup_state_index(state)
            pending.get("reject", lambda _: None)(Exception(error_msg))
        return 200, _html_error(error_msg), None

    if not code:
        return 400, _html_error("No authorization code provided"), None

    if state not in _pending_auths:
        return 400, _html_error("Invalid or expired state parameter"), None

    pending = _pending_auths.pop(state)
    _cleanup_state_index(state)
    pending.get("resolve", lambda _: None)(code)
    return 200, _HTML_SUCCESS, code


def _cleanup_state_index(oauth_state: str):
    """Remove state from reverse index."""
    for name, state in list(_mcp_name_to_state.items()):
        if state == oauth_state:
            del _mcp_name_to_state[name]
            break


async def ensure_oauth_running(redirect_uri: str | None = None):
    """Start the OAuth callback HTTP server if not already running."""
    global _callback_server, _current_port, _current_path

    port, path = parse_redirect_uri(redirect_uri)

    if _callback_server and (_current_port != port or _current_path != path):
        await stop_oauth_server()
        _callback_server = None

    if _callback_server:
        return

    _current_port = port
    _current_path = path

    async def _handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            return

        method = request_line.decode("utf-8", errors="replace").strip()
        # Read headers
        headers = b""
        while True:
            line = await reader.readline()
            headers += line
            if line == b"\r\n":
                break

        # Parse URL from request line
        parts = method.split(" ")
        url_path = parts[1] if len(parts) > 1 else "/"

        # Handle the callback
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url_path)
        params = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]
        error_description = params.get("error_description", [None])[0]

        status, body, _ = await _handle_callback(code, state, error, error_description)

        response = (
            f"HTTP/1.1 {status} {'OK' if status == 200 else 'Error'}\r\n"
            f"Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body.encode())}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        writer.write(response.encode())
        await writer.drain()
        writer.close()

    try:
        _callback_server = await asyncio.start_server(
            _handle_request, "127.0.0.1", _current_port,
        )
        logger.info("OAuth callback server started on port %s", _current_port)
    except Exception as e:
        logger.warning("OAuth callback server could not start: %s", e)


def wait_for_callback(oauth_state: str, mcp_name: str | None = None) -> asyncio.Future:
    """Wait for an OAuth callback with the given state."""
    if mcp_name:
        _mcp_name_to_state[mcp_name] = oauth_state

    fut: asyncio.Future = asyncio.Future()

    def _timeout():
        if not fut.done():
            if oauth_state in _pending_auths:
                del _pending_auths[oauth_state]
                if mcp_name and mcp_name in _mcp_name_to_state:
                    del _mcp_name_to_state[mcp_name]
            fut.set_exception(TimeoutError("OAuth callback timeout"))

    handle = asyncio.get_event_loop().call_later(_CALLBACK_TIMEOUT_MS, _timeout)

    _pending_auths[oauth_state] = {
        "resolve": lambda code: fut.set_result(code) if not fut.done() else None,
        "reject": lambda err: fut.set_exception(err) if not fut.done() else None,
        "timeout": handle,
    }
    return fut


def cancel_pending_oauth(mcp_name: str):
    """Cancel a pending OAuth authorization for a given MCP server."""
    oauth_state = _mcp_name_to_state.get(mcp_name)
    key = oauth_state or mcp_name
    pending = _pending_auths.get(key)
    if pending:
        timeout = pending.get("timeout")
        if timeout:
            timeout.cancel()
        del _pending_auths[key]
        if mcp_name in _mcp_name_to_state:
            del _mcp_name_to_state[mcp_name]
        reject = pending.get("reject")
        if reject:
            reject(Exception("Authorization cancelled"))


async def stop_oauth_server():
    """Stop the OAuth callback server and reject all pending callbacks."""
    global _callback_server
    if _callback_server:
        _callback_server.close()
        await _callback_server.wait_closed()
        _callback_server = None
        logger.info("OAuth callback server stopped")

    for state, pending in list(_pending_auths.items()):
        timeout = pending.get("timeout")
        if timeout:
            timeout.cancel()
        reject = pending.get("reject")
        if reject:
            reject(Exception("OAuth callback server stopped"))
    _pending_auths.clear()
    _mcp_name_to_state.clear()


def is_oauth_running() -> bool:
    """Check if the OAuth callback server is running."""
    return _callback_server is not None


# ── Original MCPServer (preserved) ───────────────────────────

class MCPServer:
    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False

    @property
    def configured(self) -> bool:
        return bool(self.command)

    async def connect(self):
        if self._connected:
            return True
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**self.env} if self.env else None,
            )
            self._connected = True
            logger.info(f"[MCP] 已连接: {self.name}")
            return True
        except Exception as e:
            logger.error(f"[MCP] 连接失败 {self.name}: {e}")
            return False

    async def list_tools(self) -> list[dict]:
        if not self._connected:
            return []
        try:
            req = json.dumps({"jsonrpc": "2.0", "id": "1", "method": "tools/list"})
            self._process.stdin.write(req.encode() + b"\n")
            await self._process.stdin.drain()
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=5)
            resp = json.loads(line)
            return resp.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"[MCP] 工具列表失败 {self.name}: {e}")
            return []

    async def call_tool(self, name: str, args: dict | None = None) -> dict:
        if not self._connected:
            return {"error": "未连接"}
        try:
            req = json.dumps({
                "jsonrpc": "2.0", "id": "2", "method": "tools/call",
                "params": {"name": name, "arguments": args or {}},
            })
            self._process.stdin.write(req.encode() + b"\n")
            await self._process.stdin.drain()
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30)
            return json.loads(line).get("result", {})
        except Exception as e:
            return {"error": str(e)}

    async def disconnect(self):
        if self._process:
            self._process.terminate()
            self._connected = False


class MCPManager:
    def __init__(self):
        self._servers: dict[str, MCPServer] = {}

    def register(self, server: MCPServer):
        self._servers[server.name] = server

    def get(self, name: str) -> MCPServer | None:
        return self._servers.get(name)

    def list(self) -> list[dict]:
        return [{"name": s.name, "command": s.command, "connected": s._connected}
                for s in self._servers.values()]

    async def connect_all(self):
        for s in self._servers.values():
            await s.connect()

    async def disconnect_all(self):
        for s in self._servers.values():
            await s.disconnect()


mcp_manager = MCPManager()
