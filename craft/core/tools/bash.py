"""Shell execution tool."""

import asyncio
import os

from .registry import tool
from .session_cwd import SessionCwd
from .utils import _resolve_path

MAX_BASH_OUTPUT_BYTES = 50 * 1024
MAX_BASH_OUTPUT_LINES = 2000
DEFAULT_BASH_TIMEOUT_MS = 2 * 60 * 1000

_DELETE_COMMANDS = {"rm", "rmdir", "unlink", "shred", "del", "erase", "rd",
                    "remove-item", "ri"}


def _parse_bash_command(command: str) -> str:
    """Extract the first command name from a bash command."""
    return command.strip().split()[0] if command.strip() else ""


def _is_delete_command(command: str) -> bool:
    return _parse_bash_command(command).lower() in _DELETE_COMMANDS


@tool(name="bash", description="执行 shell 命令",
      parameters={
          "type": "object",
          "properties": {
              "command": {"type": "string", "description": "要执行的命令"},
              "timeout": {"type": "integer", "description": "超时时间(毫秒)"},
              "workdir": {"type": "string", "description": "工作目录"},
              "description": {"type": "string", "description": "命令描述(5-10 个词)"},
              "interactive": {"type": "boolean", "description": "是否交互式执行"},
          },
          "required": ["command"],
      })
async def bash(command: str, timeout: int = DEFAULT_BASH_TIMEOUT_MS,
               workdir: str = "", description: str = "",
               interactive: bool = False) -> str:
    try:
        cwd = _resolve_path(workdir) if workdir else SessionCwd._project_dir
        if not os.path.isdir(cwd):
            return f"[错误] 工作目录不存在: {cwd}"

        # Warning for delete commands
        if _is_delete_command(command) and not description:
            return ("[安全] 删除命令需要 `description` 参数说明用途. "
                    "请添加 `description=\"删除什么\"` 参数.")

        # For now, non-interactive execution via subprocess
        if interactive:
            return ("[提示] 交互式执行需要在终端中运行. 请使用: "
                    f"cd {cwd} && {command}")

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout / 1000
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"[超时] 命令执行超过 {timeout}ms"

        output = stdout.decode("utf-8", errors="replace")
        error_output = stderr.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0

        if error_output:
            output += f"\n[stderr]\n{error_output[:2000]}"

        # Truncate large output
        lines = output.split("\n")
        if len(lines) > MAX_BASH_OUTPUT_LINES:
            output = "\n".join(lines[:MAX_BASH_OUTPUT_LINES])
            output += f"\n...输出截断(显示 {MAX_BASH_OUTPUT_LINES} 行, 共 {len(lines)} 行)..."
        if len(output.encode("utf-8")) > MAX_BASH_OUTPUT_BYTES:
            output = output[:MAX_BASH_OUTPUT_BYTES] + "\n...输出截断(超过 50KB)..."

        desc = f" ({description})" if description else ""
        result = f"退出码: {exit_code}{desc}\n{output}"
        return result.strip()
    except Exception as e:
        return f"[错误] {e}"
