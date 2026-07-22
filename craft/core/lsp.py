"""
LSP 集成 — 移植自 packages/opencode/src/lsp/
Language Server Protocol 客户端管理

支持：client（创建 LSP 连接）、diagnostic（诊断格式化）、
language（文件扩展名→语言 ID 映射）、launch（服务器启动）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Language Extensions ──────────────────────────────────────
# 对应 TS lsp/language.ts

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".abap": "abap",
    ".bat": "bat",
    ".bib": "bibtex",
    ".c": "c",
    ".cc": "cpp",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".coffee": "coffeescript",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".cxx": "cpp",
    ".dart": "dart",
    ".dockerfile": "dockerfile",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".fs": "fsharp",
    ".go": "go",
    ".groovy": "groovy",
    ".hs": "haskell",
    ".html": "html",
    ".java": "java",
    ".jl": "julia",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".json": "json",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".less": "less",
    ".lua": "lua",
    ".md": "markdown",
    ".mjs": "javascript",
    ".ml": "ocaml",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".scss": "scss",
    ".sh": "shellscript",
    ".sql": "sql",
    ".swift": "swift",
    ".tex": "latex",
    ".tf": "terraform",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".vue": "vue",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".zig": "zig",
    ".nix": "nix",
    ".svelte": "svelte",
}


def get_language_id(filepath: str) -> str:
    """Map a file extension to its LSP language ID."""
    ext = os.path.splitext(filepath)[1].lower()
    return LANGUAGE_EXTENSIONS.get(ext, "plaintext")


# ── Diagnostics ──────────────────────────────────────────────
# 对应 TS lsp/diagnostic.ts

MAX_PER_FILE = 20

SEVERITY_MAP: dict[int, str] = {
    1: "ERROR",
    2: "WARN",
    3: "INFO",
    4: "HINT",
}


@dataclass
class LSPDiagnostic:
    """A single LSP diagnostic item."""
    range: dict
    severity: int = 1
    message: str = ""
    source: str | None = None
    code: str | int | None = None


def pretty_diagnostic(diagnostic: LSPDiagnostic | dict) -> str:
    """Format a single diagnostic for human-readable output."""
    if isinstance(diagnostic, dict):
        severity = diagnostic.get("severity", 1)
        message = diagnostic.get("message", "")
        line = diagnostic.get("range", {}).get("start", {}).get("line", 0) + 1
        col = diagnostic.get("range", {}).get("start", {}).get("character", 0) + 1
    else:
        severity = diagnostic.severity
        message = diagnostic.message
        line = diagnostic.range.get("start", {}).get("line", 0) + 1
        col = diagnostic.range.get("start", {}).get("character", 0) + 1

    sev = SEVERITY_MAP.get(severity, "UNKNOWN")
    return f"{sev} [{line}:{col}] {message}"


def report_diagnostics(filepath: str, issues: list[LSPDiagnostic | dict]) -> str:
    """Format a set of diagnostics for a file into an XML-like block.

    Only errors (severity=1) are included, with a limit per file.
    """
    errors = [
        d for d in issues
        if (isinstance(d, dict) and d.get("severity") == 1)
        or (isinstance(d, LSPDiagnostic) and d.severity == 1)
    ]
    if not errors:
        return ""
    limited = errors[:MAX_PER_FILE]
    more = len(errors) - MAX_PER_FILE
    lines = "\n".join(pretty_diagnostic(d) for d in limited)
    suffix = f"\n... and {more} more" if more > 0 else ""
    return f"<diagnostics file=\"{filepath}\">\n{lines}{suffix}\n</diagnostics>"


# ── Launch ───────────────────────────────────────────────────
# 对应 TS lsp/launch.ts

@dataclass
class LaunchConfig:
    """Configuration for launching an LSP server."""
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None


def launch(config: LaunchConfig) -> asyncio.subprocess.Process | None:
    """Spawn an LSP server process with stdin/stdout/stderr pipes."""
    async def _launch() -> asyncio.subprocess.Process | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                config.command, *config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=config.env,
                cwd=config.cwd,
            )
            return proc
        except Exception as e:
            logger.error("[LSP] launch failed: %s: %s", config.command, e)
            return None
    return _launch


# ── LSP Client ───────────────────────────────────────────────
# 对应 TS lsp/client.ts

INITIALIZE_TIMEOUT = 45_000  # 45 seconds


@dataclass
class LSPNotification:
    """A notification received from the LSP server."""
    method: str
    params: dict | None = None


@dataclass
class LSPClientInfo:
    """Information about a connected LSP client."""
    server_id: str
    root: str
    process: asyncio.subprocess.Process
    capabilities: dict = field(default_factory=dict)
    diagnostics: dict[str, list[dict]] = field(default_factory=dict)

    _request_id: int = 0
    _pending: dict[int, asyncio.Future] = field(default_factory=dict)

    def next_id(self) -> int:
        self._request_id += 1
        return self._request_id


async def create_lsp_client(
    server_id: str,
    process: asyncio.subprocess.Process,
    root: str,
    directory: str,
    initialization_options: dict | None = None,
    on_diagnostics: Callable[[str, str], None] | None = None,
) -> LSPClientInfo | None:
    """Create an LSP client connected to an already-running server process.

    Sends initialize + initialized handshake and sets up notification handlers.
    """
    if not process.stdin or not process.stdout:
        logger.error("[LSP] process has no stdin/stdout pipes")
        return None

    client = LSPClientInfo(
        server_id=server_id,
        root=root,
        process=process,
        diagnostics={},
    )

    # Set up notification reader
    async def _read_notifications():
        buf = b""
        while True:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=300)
                if not chunk:
                    break
                buf += chunk
                # Parse Content-Length headers and JSON-RPC messages
                while b"\r\n\r\n" in buf:
                    header, rest = buf.split(b"\r\n\r\n", 1)
                    header_str = header.decode("utf-8", errors="replace")
                    content_length = 0
                    for line in header_str.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())

                    if len(rest) < content_length:
                        break  # Wait for more data

                    body = rest[:content_length]
                    buf = rest[content_length:]

                    try:
                        msg = json.loads(body.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue

                    # Handle responses
                    if "id" in msg:
                        fut = client._pending.get(msg["id"])
                        if fut and not fut.done():
                            fut.set_result(msg)

                    # Handle notifications
                    if msg.get("method") == "textDocument/publishDiagnostics":
                        params = msg.get("params", {})
                        uri = params.get("uri", "")
                        filepath = uri.replace("file://", "")
                        diagnostics_list = params.get("diagnostics", [])
                        client.diagnostics[filepath] = diagnostics_list
                        logger.info("[LSP] diagnostics for %s: %d items", filepath, len(diagnostics_list))
                        if on_diagnostics:
                            on_diagnostics(server_id, filepath)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("[LSP] notification reader error: %s", e)
                break

    reader_task = asyncio.create_task(_read_notifications())

    async def _request(method: str, params: dict | None = None) -> dict | None:
        req_id = client.next_id()
        fut: asyncio.Future = asyncio.Future()
        client._pending[req_id] = fut

        req = json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        })
        header = f"Content-Length: {len(req)}\r\n\r\n"
        process.stdin.write((header + req).encode())
        await process.stdin.drain()

        try:
            return await asyncio.wait_for(fut, timeout=30)
        except asyncio.TimeoutError:
            client._pending.pop(req_id, None)
            return None

    async def _notify(method: str, params: dict | None = None):
        req = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        })
        header = f"Content-Length: {len(req)}\r\n\r\n"
        process.stdin.write((header + req).encode())
        await process.stdin.drain()

    # Send initialize
    logger.info("[LSP] sending initialize to %s", server_id)
    init_params = {
        "processId": process.pid,
        "rootUri": Path(root).as_uri(),
        "capabilities": {
            "textDocument": {
                "synchronization": {"didOpen": True, "didChange": True},
                "publishDiagnostics": {"versionSupport": True},
            },
            "workspace": {"configuration": True},
            "window": {"workDoneProgress": True},
        },
        "initializationOptions": initialization_options or {},
        "workspaceFolders": [{"name": "workspace", "uri": Path(root).as_uri()}],
    }
    init_result = await _request("initialize", init_params)
    if init_result is None:
        logger.error("[LSP] initialize timed out for %s", server_id)
        reader_task.cancel()
        return None

    client.capabilities = init_result.get("result", {}).get("capabilities", {})
    await _notify("initialized", {})

    # Send workspace configuration if initialization options provided
    if initialization_options:
        await _notify("workspace/didChangeConfiguration", {
            "settings": initialization_options,
        })

    logger.info("[LSP] client initialized: %s", server_id)

    client_handle = client

    async def open_document(filepath: str):
        """Notify LSP that a document was opened."""
        abs_path = filepath if os.path.isabs(filepath) else os.path.join(directory, filepath)
        try:
            with open(abs_path) as f:
                text = f.read()
        except Exception:
            text = ""

        lang_id = get_language_id(abs_path)
        file_uri = Path(abs_path).as_uri()

        await _notify("textDocument/didOpen", {
            "textDocument": {
                "uri": file_uri,
                "languageId": lang_id,
                "version": 0,
                "text": text,
            },
        })
        logger.info("[LSP] didOpen: %s", filepath)

    async def change_document(filepath: str, text: str, version: int = 1):
        """Notify LSP of a document change."""
        abs_path = filepath if os.path.isabs(filepath) else os.path.join(directory, filepath)
        file_uri = Path(abs_path).as_uri()

        await _notify("textDocument/didChange", {
            "textDocument": {"uri": file_uri, "version": version},
            "contentChanges": [{"text": text}],
        })

    async def shutdown():
        """Shut down the LSP connection."""
        logger.info("[LSP] shutting down %s", server_id)
        await _request("shutdown", {})
        await _notify("exit", {})
        reader_task.cancel()
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()

    client_handle.open_document = open_document  # type: ignore
    client_handle.change_document = change_document  # type: ignore
    client_handle.shutdown = shutdown  # type: ignore

    return client_handle


# ── Original LSPServer (preserved and enhanced) ──────────────

class LSPServer:
    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 languages: list[str] | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.languages = languages or []
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def start(self) -> bool:
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 发送 initialize 请求
            result = await self._request("initialize", {
                "processId": None,
                "capabilities": {},
                "rootUri": None,
            })
            await self._notify("initialized", {})
            return result is not None
        except Exception as e:
            logger.error(f"[LSP] 启动失败 {self.name}: {e}")
            return False

    async def _request(self, method: str, params: dict) -> dict | None:
        if not self._process:
            return None
        self._request_id += 1
        req = json.dumps({
            "jsonrpc": "2.0", "id": self._request_id,
            "method": method, "params": params,
        })
        header = f"Content-Length: {len(req)}\r\n\r\n"
        self._process.stdin.write((header + req).encode())
        await self._process.stdin.drain()
        try:
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=10)
            return {"ok": True}
        except Exception:
            return None

    async def _notify(self, method: str, params: dict):
        if not self._process:
            return
        req = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
        header = f"Content-Length: {len(req)}\r\n\r\n"
        self._process.stdin.write((header + req).encode())
        await self._process.stdin.drain()

    async def hover(self, filepath: str, line: int, col: int) -> str | None:
        return None

    async def completion(self, filepath: str, line: int, col: int) -> list[str]:
        return []

    async def definition(self, filepath: str, line: int, col: int) -> dict | None:
        return None

    async def stop(self):
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()


class LSPManager:
    def __init__(self):
        self._servers: dict[str, LSPServer] = {}

    def register(self, server: LSPServer):
        self._servers[server.name] = server

    def get(self, name: str) -> LSPServer | None:
        return self._servers.get(name)

    def for_language(self, language: str) -> LSPServer | None:
        for s in self._servers.values():
            if language in s.languages:
                return s
        return None

    def list(self) -> list[dict]:
        return [{"name": s.name, "command": s.command, "languages": s.languages}
                for s in self._servers.values()]


lsp_manager = LSPManager()
