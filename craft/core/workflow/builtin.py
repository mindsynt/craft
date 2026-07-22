"""
内置工作流 — 移植自 packages/opencode/src/workflow/builtin.ts
"""

from __future__ import annotations

from dataclasses import dataclass

from craft.core.workflow.meta import WorkflowPhase


@dataclass
class BuiltinEntry:
    name: str = ""
    description: str = ""
    when_to_use: str | None = None
    phases: list[WorkflowPhase] | None = None
    script: str = ""


class BuiltinWorkflowRegistry:
    """内置工作流注册表 — 移植自 builtin.ts"""

    def __init__(self):
        self._entries: dict[str, BuiltinEntry] = {}
        self._init_defaults()

    def _init_defaults(self):
        """初始化默认内置工作流"""
        self.register(BuiltinEntry(
            name="deep-research",
            description="Deep research on a topic with parallel agent exploration",
            when_to_use="When you need comprehensive research on a topic",
            phases=[WorkflowPhase(title="Research", detail="Parallel research phase")],
            script="# built-in deep research workflow\nasync function main() {}\nmain();",
        ))
        self.register(BuiltinEntry(
            name="fact-check",
            description="Fact-check claims with evidence gathering",
            phases=[WorkflowPhase(title="Verify", detail="Evidence verification phase")],
            script="# built-in fact check workflow\nasync function main() {}\nmain();",
        ))
        self.register(BuiltinEntry(
            name="compose",
            description="Compose and refine content with multiple passes",
            phases=[WorkflowPhase(title="Draft"), WorkflowPhase(title="Review")],
            script="# built-in compose workflow\nasync function main() {}\nmain();",
        ))

    def register(self, entry: BuiltinEntry):
        self._entries[entry.name] = entry

    def list(self) -> list[BuiltinEntry]:
        return sorted(self._entries.values(), key=lambda e: e.name)

    def get(self, name: str) -> BuiltinEntry | None:
        return self._entries.get(name)


builtin_registry = BuiltinWorkflowRegistry()
