"""
命令系统 — 移植自 packages/opencode/src/command/
CLI 命令注册、参数解析、帮助生成
"""

from __future__ import annotations

from typing import Any, Callable


class Command:
    def __init__(self, name: str, description: str = "", handler: Callable | None = None,
                 aliases: list[str] | None = None):
        self.name = name
        self.description = description
        self.handler = handler
        self.aliases = aliases or []
        self.subcommands: dict[str, Command] = {}
        self.options: list[dict] = []

    def add_subcommand(self, cmd: Command):
        self.subcommands[cmd.name] = cmd
        for alias in cmd.aliases:
            self.subcommands[alias] = cmd

    def add_option(self, name: str, description: str = "", type: str = "str", required: bool = False):
        self.options.append({"name": name, "description": description, "type": type, "required": required})

    async def run(self, args: list[str] | None = None) -> Any:
        args = args or []
        if args and args[0] in self.subcommands:
            return await self.subcommands[args[0]].run(args[1:])
        if self.handler:
            r = self.handler(args)
            if hasattr(r, "__await__"):
                return await r
            return r
        return None

    def help_text(self) -> str:
        lines = [f"  {self.name} - {self.description}"]
        if self.options:
            lines.append("    选项:")
            for opt in self.options:
                req = " (必填)" if opt.get("required") else ""
                lines.append(f"      --{opt['name']} {opt.get('type','str')}{req} - {opt.get('description','')}")
        if self.subcommands:
            lines.append("    子命令:")
            for name, cmd in sorted(self.subcommands.items()):
                if name == cmd.name:
                    lines.append(f"      {name:20s} {cmd.description}")
        return "\n".join(lines)


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, Command] = {}

    def register(self, cmd: Command):
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._commands[alias] = cmd

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def list(self) -> list[Command]:
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        return result

    async def execute(self, name: str, args: list[str] | None = None) -> Any:
        cmd = self._commands.get(name)
        if cmd:
            return await cmd.run(args)
        raise ValueError(f"未知命令: {name}")


command_registry = CommandRegistry()
