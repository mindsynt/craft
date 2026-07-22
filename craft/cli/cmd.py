"""CLI cmd wrapper — 移植自 packages/opencode/src/cli/cmd/cmd.ts

Provides a typed command definition helper for CLI registration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CmdDef:
    """A command definition matching the CLI command pattern."""
    command: str
    describe: str
    builder: Callable | None = None
    handler: Callable | None = None
    subcommands: list[CmdDef] = field(default_factory=list)

    def add_subcommand(self, cmd: CmdDef):
        self.subcommands.append(cmd)

    async def run(self, args: dict[str, Any] | None = None):
        if self.handler:
            await self.handler(args or {})


def cmd(command: str, describe: str = "",
        builder: Callable | None = None) -> Callable:
    """Decorator to define a CLI command.

    Usage:
        @cmd("serve", "Start the server")
        async def serve_handler(args):
            ...
    """
    def decorator(handler: Callable) -> Callable:
        handler._cmd_def = CmdDef(
            command=command,
            describe=describe,
            builder=builder,
            handler=handler,
        )
        return handler
    return decorator


def get_cmd_def(fn: Callable) -> CmdDef | None:
    """Get the CmdDef attached to a function by the @cmd decorator."""
    return getattr(fn, "_cmd_def", None)
