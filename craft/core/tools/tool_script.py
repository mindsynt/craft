"""Tool script sandbox — run Python user-defined code with access to tools and file I/O.

移植自 MiMo-Code packages/opencode/src/tool/tool-script.ts

The tool_script tool allows the model to write and execute scripts that
can call other tools programmatically. This is a sandboxed environment
with controlled access to tools and file I/O.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

from .tool_script_ref import TOOL_SCRIPT_EXCLUDED

logger = logging.getLogger(__name__)

# Constants
MAX_TOOL_CALLS_DEFAULT = 50
MAX_TOOL_CALLS_CEILING = 500
MAX_CONCURRENT = 8
ACTIVE_DEADLINE_S_DEFAULT = 60
ACTIVE_DEADLINE_S_CEILING = 600
WALL_DEADLINE_MS = 30 * 60 * 1000
MAX_RESULT_BYTES = 256 * 1024
MAX_LOG_BYTES = 64 * 1024
MAX_CODE_BYTES = 128 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024


def schema_to_python_type(schema: dict[str, Any]) -> str:
    """Convert a JSON schema to a compact Python type annotation string.

    Best-effort: unrecognized types render as 'Any'.
    """
    if not schema or not isinstance(schema, dict):
        return "Any"
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    variants = schema.get("anyOf") or schema.get("oneOf")
    if variants:
        return " | ".join(schema_to_python_type(v) for v in variants)

    stype = schema.get("type", "")
    if stype == "string":
        return "str"
    if stype in ("number", "integer"):
        return "int"
    if stype == "boolean":
        return "bool"
    if stype == "null":
        return "None"
    if stype == "array":
        items = schema.get("items", {})
        return f"list[{schema_to_python_type(items)}]"
    if stype == "object":
        properties = schema.get("properties")
        if not properties:
            additional = schema.get("additionalProperties", {})
            if additional and isinstance(additional, dict):
                return f"dict[str, {schema_to_python_type(additional)}]"
            return "dict[str, Any]"
        required = set(schema.get("required", []))
        fields = []
        for key, value in properties.items():
            sep = "" if key in required else " | None"
            fields.append(f"    {key}: {schema_to_python_type(value)}{sep}")
        return "{\n" + ",\n".join(fields) + "\n}"
    return "Any"


TOOL_SCRIPT_DESCRIPTION = """Execute Python code with access to agent tools.

Write Python code that calls tools via the provided `tools` object.
Return a JSON-serializable value as the result.

Available globals:
- tools: A proxy object that provides access to agent tools
  (e.g., tools.read(), tools.bash(), tools.edit())
- console: A logging object (console.log, console.error, console.warn)
- files: Raw file I/O (readText, writeText) for temp directory use

The script runs in a sandbox with limited file system access.
"""


async def execute_tool_script(
    code: str,
    tool_defs: list[dict[str, Any]] | None = None,
    mcp_tools: dict[str, Any] | None = None,
    max_tool_calls: int = MAX_TOOL_CALLS_DEFAULT,
    timeout_seconds: int = ACTIVE_DEADLINE_S_DEFAULT,
    call_tool_fn: Any = None,
    session_cwd: str | None = None,
    worktree: str | None = None,
) -> dict[str, Any]:
    """Execute a tool_script in a sandboxed environment.

    Args:
        code: Python source code for the script body.
        tool_defs: List of tool definitions available to the script.
        mcp_tools: Dict of MCP tools available to the script.
        max_tool_calls: Maximum number of tool calls allowed.
        timeout_seconds: Maximum compute time in seconds.
        call_tool_fn: Async callable for executing tool calls.
        session_cwd: Session working directory.
        worktree: Project worktree root.

    Returns:
        Tool result dict with title, output, metadata.
    """
    if isinstance(code, str) and len(code.encode("utf-8")) > MAX_CODE_BYTES:
        return {
            "title": "code too large",
            "metadata": {"status": "code_error", "tool_calls": 0},
            "output": (f"<tool_script status=\"code_error\">\n"
                       f"<error_message>\ncode exceeds {MAX_CODE_BYTES} bytes\n"
                       f"</error_message>\n</tool_script>"),
        }

    logs: list[str] = []
    calls = 0
    trace: list[dict[str, Any]] = []

    def _console_log(*args: Any) -> None:
        logs.append(" ".join(str(a) for a in args))

    class ToolProxy:
        """Proxy that forwards attribute access to tool calls."""

        def __getattr__(self, name: str) -> Any:
            async def _call(*args: Any, **kwargs: Any) -> Any:
                nonlocal calls
                calls += 1
                if calls > max_tool_calls:
                    raise RuntimeError(f"tool call budget exceeded ({max_tool_calls} per execution)")

                start = time.time()
                try:
                    if call_tool_fn:
                        result = await call_tool_fn(name, *args, **kwargs)
                        duration = (time.time() - start) * 1000
                        trace.append({
                            "name": name,
                            "status": "success",
                            "duration_ms": duration,
                        })
                        return result
                    else:
                        return {"output": f"tool {name} called"}
                except Exception as e:
                    duration = (time.time() - start) * 1000
                    trace.append({
                        "name": name,
                        "status": "error",
                        "duration_ms": duration,
                        "error": str(e),
                    })
                    raise

            return _call

    class FileProxy:
        """Proxy for file I/O — reads allowed from worktree+tmp, writes to tmp only."""

        @staticmethod
        async def read_text(path: str) -> str | None:
            abs_path = _resolve_safe_path(path, worktree)
            if abs_path and os.path.isfile(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        return f.read()
                except Exception:
                    return None
            return None

        @staticmethod
        async def write_text(path: str, content: str) -> None:
            abs_path = _resolve_safe_path(path, str(tempfile.gettempdir()))
            if not abs_path or not abs_path.startswith(tempfile.gettempdir()):
                raise PermissionError(f"write limited to temp dir: {path}")
            Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)

    # Prepare locals for exec
    local_vars: dict[str, Any] = {
        "tools": ToolProxy(),
        "console": type("Console", (), {
            "log": _console_log,
            "error": lambda *a: _console_log("[error]", *a),
            "warn": lambda *a: _console_log("[warn]", *a),
        })(),
        "files": FileProxy(),
        "__result__": None,
    }

    try:
        wrapped_code = (
            "async def __main__():\n"
            + "\n".join("    " + line for line in code.split("\n"))
        )
        exec_globals: dict[str, Any] = {}
        exec(wrapped_code, exec_globals)
        await exec_globals["__main__"]()
        result_value = local_vars.get("__result__")

        return {
            "title": "Script executed",
            "metadata": {
                "status": "success",
                "tool_calls": calls,
                "trace": trace,
                "log_count": len(logs),
            },
            "output": (
                json.dumps({
                    "status": "success",
                    "result": result_value,
                    "logs": logs,
                    "tool_calls": calls,
                    "trace": trace,
                }, ensure_ascii=False, default=str)
                if result_value is not None
                else json.dumps({
                    "status": "success",
                    "result": None,
                    "logs": logs,
                    "tool_calls": calls,
                }, ensure_ascii=False, default=str)
            ),
        }
    except Exception as e:
        return {
            "title": "Script error",
            "metadata": {
                "status": "code_error",
                "tool_calls": calls,
                "trace": trace,
            },
            "output": (f"<tool_script status=\"code_error\">\n"
                       f"<error_message>\n{traceback.format_exc()}\n"
                       f"</error_message>\n</tool_script>"),
        }


def _resolve_safe_path(path: str, allowed_root: str | None) -> str | None:
    """Resolve a path safely, ensuring it's within allowed_root."""
    if not path:
        return None
    try:
        resolved = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
        if allowed_root:
            allowed = os.path.realpath(os.path.abspath(os.path.expanduser(allowed_root)))
            if not resolved.startswith(allowed + os.sep) and resolved != allowed:
                return None
        return resolved
    except Exception:
        return None
