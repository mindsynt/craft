"""Shell wrap — 移植自 packages/opencode/src/tool/shell-wrap.ts

Wraps a tool definition for shell-style invocation. The shell wrapper accepts
a multi-line ``script`` parameter, parses it into individual commands via
shell_tokenize, and executes them sequentially, stopping on first failure.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from .shell_tokenize import tokenize, Argv, ParseError


def _escape_attr(s: str) -> str:
    """Escape a string for use in an XML attribute."""
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _operation_label(parsed: Any) -> str:
    """Derive a string label for the operation XML attribute.

    Tolerates both flat ``{operation: "run"}`` and nested
    ``{operation: {action: "create"}}`` discriminator shapes.
    """
    if not isinstance(parsed, dict):
        return "?"
    op = parsed.get("operation")
    if isinstance(op, str):
        return op
    if isinstance(op, dict) and isinstance(op.get("action"), str):
        return op["action"]
    return "?"


def _describe_failure(err: Any) -> str:
    if isinstance(err, Exception):
        return str(err)
    if isinstance(err, ParseError):
        return f"{err.kind}: {err.detail}"
    return str(err)


def _format_ok_command(index: int, operation: str, body: str) -> str:
    return f'<command index="{index}" operation="{_escape_attr(operation)}">\n{body}\n</command>'


def _format_failed_command(index: int, operation: str, body: str) -> str:
    return f'<command index="{index}" operation="{_escape_attr(operation)}" failed="true">\n{body}\n</command>'


def _format_failed_command_no_verb(body: str) -> str:
    return f'<command failed="true">\n{body}\n</command>'


def _format_notice(body: str) -> str:
    return f"<notice>\n{body}\n</notice>"


def _repair_json_escapes(script: str) -> str | None:
    """Repair JSON double-escaped newlines/tabs.

    Only used when the strict parse failed and the repaired re-parse succeeds.
    """
    if "\\n" not in script and "\\t" not in script:
        return None
    return script.replace("\\n", "\n").replace("\\t", "\t")


def _format_parse_error(tool_id: str, err: Any) -> str:
    if isinstance(err, ParseError):
        line = err.line or "?"
        return f"{tool_id}: parse error at line {line}\n  {err.detail or err.kind}"
    if isinstance(err, Exception):
        return f"{tool_id}: parse error\n  {str(err)}"
    return f"{tool_id}: parse error\n  {str(err)}"


def shell_wrap(
    tool_id: str,
    shell_description: str,
    shell_parse_fn: Callable[[Any], list[Argv] | ParseError],
    execute_fn: Callable[[dict, Any], dict],
) -> Callable:
    """Wrap a tool for shell-style invocation.

    Args:
        tool_id: Tool identifier (e.g., "actor", "task").
        shell_description: Description shown when invoked in shell mode.
        shell_parse_fn: Function that takes an args dict and returns
                        list[Argv] or ParseError.
        execute_fn: Function that takes (parsed_args, context) and returns
                    result dict with {"title": str, "output": str, "metadata": dict}.

    Returns:
        An execute function that accepts {"script": str, ...} and runs commands.
    """
    def _execute(args: dict, ctx: Any) -> dict:
        script = args.get("script", "")
        if not isinstance(script, str) or not script.strip():
            # Try tool-specific recovery for JSON-shape args
            recovered = args.get("operation")
            if recovered is not None:
                result = execute_fn({"operation": recovered}, ctx)
                op = _operation_label(recovered)
                return {
                    "title": f"{tool_id}: {op}",
                    "output": result.get("output", ""),
                    "metadata": {
                        **(result.get("metadata") or {}),
                        "commands": 1,
                        "success": 1,
                    },
                }
            return {
                "title": f"{tool_id}: missing script",
                "output": _format_failed_command_no_verb(
                    f"{tool_id}: this tool takes a single `script` string (shell-style), not JSON fields.\n"
                    f"Put the command in `script`, e.g.:  {tool_id} <verb> ..."
                ),
                "metadata": {"commands": 0, "success": 0},
            }

        # Parse the script
        rescued = False
        parse_result = shell_parse_fn({"script": script})

        if isinstance(parse_result, ParseError):
            repaired = _repair_json_escapes(script)
            if repaired is not None:
                retry = shell_parse_fn({"script": repaired})
                if isinstance(retry, list):
                    parse_result = retry
                    rescued = True

        if isinstance(parse_result, ParseError):
            return {
                "title": f"{tool_id}: parse error",
                "output": _format_failed_command_no_verb(
                    _format_parse_error(tool_id, parse_result)
                ),
                "metadata": {"commands": 0, "success": 0},
            }

        parsed_list: list[Argv] = parse_result
        if not parsed_list:
            return {
                "title": f"{tool_id}: empty script",
                "output": _format_failed_command_no_verb(
                    f"{tool_id}: no commands found in script"
                ),
                "metadata": {"commands": 0, "success": 0},
            }

        blocks: list[str] = []
        if rescued:
            blocks.append(
                _format_notice(
                    f"{tool_id}: your script had no real line breaks — "
                    r"literal \n / \t were read as newlines/tabs.\n"
                    "Emit REAL line breaks in the script, not a doubled backslash."
                )
            )

        last_metadata: dict = {}
        success = 0
        for i, parsed in enumerate(parsed_list):
            # Reconstruct args dict from tokens
            command_args = {"script": " ".join(parsed.tokens)}
            operation = _operation_label(command_args)
            try:
                result = execute_fn(command_args, ctx)
                if isinstance(result, dict) and result.get("status") == "error":
                    blocks.append(
                        _format_failed_command(i + 1, operation, result.get("output", str(result)))
                    )
                    if i + 1 < len(parsed_list):
                        blocks.append(
                            f"<not-executed>commands #{i + 2}..#{len(parsed_list)}</not-executed>"
                        )
                    return {
                        "title": f"{tool_id}: command #{i + 1} failed",
                        "output": "\n".join(blocks),
                        "metadata": {"commands": len(parsed_list), "success": success},
                    }
                success += 1
                last_metadata: dict = {}
                if isinstance(result, dict):
                    last_metadata = result.get("metadata") or {}
                blocks.append(
                    _format_ok_command(i + 1, operation, result.get("output", "") if isinstance(result, dict) else str(result))
                )
            except Exception as e:
                blocks.append(
                    _format_failed_command(i + 1, operation, _describe_failure(e))
                )
                if i + 1 < len(parsed_list):
                    blocks.append(
                        f"<not-executed>commands #{i + 2}..#{len(parsed_list)}</not-executed>"
                    )
                return {
                    "title": f"{tool_id}: command #{i + 1} failed",
                    "output": "\n".join(blocks),
                    "metadata": {"commands": len(parsed_list), "success": success},
                }

        return {
            "title": f"{tool_id}: {len(parsed_list)} command(s)",
            "output": "\n".join(blocks),
            "metadata": {**last_metadata, "commands": len(parsed_list), "success": success},
        }

    return _execute
