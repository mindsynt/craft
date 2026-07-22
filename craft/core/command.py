"""
命令系统 — 移植自 packages/opencode/src/command/
CLI 命令注册、参数解析、模板系统、默认命令
"""

from __future__ import annotations

import re
from typing import Any, Callable

from craft.core.bus import define_event


# ── 事件 ────────────────────────────────────────────────────

CommandExecutedEvent = define_event("command.executed", {
    "name": str,
    "sessionID": str,
    "arguments": str,
    "messageID": str,
})


# ── 命令信息 ───────────────────────────────────────────────

class CommandInfo:
    """命令元信息 — 对应 TS Command.Info"""

    def __init__(self, name: str, description: str = "", **kw):
        self.name = name
        self.description = description
        self.agent: str | None = kw.get("agent")
        self.model: str | None = kw.get("model")
        self.source: str | None = kw.get("source")  # "command" | "mcp" | "skill"
        self.bundled: bool | None = kw.get("bundled")
        self.subtask: bool | None = kw.get("subtask")
        self.hints: list[str] = kw.get("hints", [])
        self._template: str | None = kw.get("template")
        self._handler: Callable | None = kw.get("handler")

    @property
    def template(self) -> str | None:
        return self._template

    @template.setter
    def template(self, value: str):
        self._template = value

    @property
    def handler(self) -> Callable | None:
        return self._handler

    @handler.setter
    def handler(self, fn: Callable):
        self._handler = fn


# ── 模板辅助 ───────────────────────────────────────────────

def extract_hints(template: str) -> list[str]:
    """从模板中提取提示（$1, $2, $ARGUMENTS 等）"""
    result: list[str] = []
    numbered = re.findall(r"\$\d+", template)
    if numbered:
        for match in sorted(set(numbered)):
            result.append(match)
    if "$ARGUMENTS" in template:
        result.append("$ARGUMENTS")
    return result


# ── 默认命令名称 ────────────────────────────────────────────

DEFAULT_COMMANDS = {
    "INIT": "init",
    "REVIEW": "review",
    "DREAM": "dream",
    "DISTILL": "distill",
    "GOAL": "goal",
    "DEEP_RESEARCH": "deep-research",
    "LOOPS": "loops",
    "REBUILD": "rebuild",
}


def deep_research_template() -> str:
    return """The user wants a deep, multi-source, fact-checked research report.

Research request:
$ARGUMENTS

If the request is underspecified (missing scope, constraints, region, time range, etc.),
ask 2-3 brief clarifying questions FIRST, then weave the answers into a refined question.

When the request is specific enough, run the built-in deep-research workflow:
  workflow({ operation: "run", name: "deep-research", args: "<the refined research question>" })

Pass the full refined question as `args`. The workflow fans out web searches, fetches sources,
adversarially verifies claims, and returns a cited report; relay its result to the user."""


def default_init_template(worktree: str = "") -> str:
    """初始化命令模板"""
    return f"guided AGENTS.md setup at {worktree}" if worktree else "guided AGENTS.md setup"


def default_review_template(worktree: str = "") -> str:
    return f"review changes [commit|branch|pr] at {worktree}" if worktree else "review changes [commit|branch|pr], defaults to uncommitted"


# ── 命令 ────────────────────────────────────────────────────

class Command:
    """单个命令"""

    def __init__(self, name: str, description: str = "", handler: Callable | None = None,
                 aliases: list[str] | None = None):
        self.name = name
        self.description = description
        self.handler = handler
        self.aliases = aliases or []
        self.subcommands: dict[str, Command] = {}
        self.options: list[dict] = []
        self.info: CommandInfo | None = None

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
                lines.append(f"      --{opt['name']} {opt.get('type', 'str')}{req} - {opt.get('description', '')}")
        if self.subcommands:
            lines.append("    子命令:")
            for name, cmd in sorted(self.subcommands.items()):
                if name == cmd.name:
                    lines.append(f"      {name:20s} {cmd.description}")
        return "\n".join(lines)


class CommandRegistry:
    """命令注册表 — 对应 TS Command.Service"""

    def __init__(self):
        self._commands: dict[str, CommandInfo] = {}

    def register(self, cmd: CommandInfo):
        self._commands[cmd.name] = cmd

    def get(self, name: str) -> CommandInfo | None:
        return self._commands.get(name)

    def list(self) -> list[CommandInfo]:
        return list(self._commands.values())

    def add_defaults(self, worktree: str = ""):
        """注册默认命令（同 TS Command.layer 中的初始化逻辑）"""
        defaults = [
            CommandInfo(
                DEFAULT_COMMANDS["INIT"],
                description="guided AGENTS.md setup",
                source="command",
                template=default_init_template(worktree),
                hints=extract_hints(default_init_template(worktree)),
            ),
            CommandInfo(
                DEFAULT_COMMANDS["REVIEW"],
                description="review changes [commit|branch|pr], defaults to uncommitted",
                source="command",
                template=default_review_template(worktree),
                subtask=True,
                hints=extract_hints(default_review_template(worktree)),
            ),
            CommandInfo(
                DEFAULT_COMMANDS["DREAM"],
                description="manually consolidate project memory from memory files and raw trajectory",
                agent="dream",
                source="command",
                template="""Run one manual dream memory consolidation pass for the current project.

User focus or constraints:
$ARGUMENTS""",
                hints=["$ARGUMENTS"],
            ),
            CommandInfo(
                DEFAULT_COMMANDS["DISTILL"],
                description="find repeated workflows in recent work and package them into skills, subagents, or commands",
                agent="distill",
                source="command",
                template="""Run one manual distill pass for the current project.

User focus or constraints:
$ARGUMENTS""",
                hints=["$ARGUMENTS"],
            ),
            CommandInfo(
                DEFAULT_COMMANDS["GOAL"],
                description='set a stop-condition goal; runs until a judge says it\'s met. /goal clear to abort',
                source="command",
                template="$ARGUMENTS",
                hints=["$ARGUMENTS"],
            ),
            CommandInfo(
                DEFAULT_COMMANDS["REBUILD"],
                description="rebuild the conversation context now from the latest checkpoint (frees context; keeps recent messages)",
                source="command",
                template="$ARGUMENTS",
                hints=["$ARGUMENTS"],
            ),
            CommandInfo(
                DEFAULT_COMMANDS["DEEP_RESEARCH"],
                description="deep multi-source, fact-checked research report (runs the deep-research workflow)",
                source="command",
                bundled=True,
                template=deep_research_template(),
                hints=["$ARGUMENTS"],
            ),
        ]
        for cmd in defaults:
            self.register(cmd)

    async def execute(self, name: str, args: list[str] | None = None) -> Any:
        cmd = self._commands.get(name)
        if cmd and cmd.handler:
            r = cmd.handler(args or [])
            if hasattr(r, "__await__"):
                return await r
            return r
        if cmd:
            return None
        raise ValueError(f"未知命令: {name}")


command_registry = CommandRegistry()
command_registry.add_defaults()
