"""
Skill 系统 — 移植自 packages/opencode/src/skill/
可复用的自动化工作流：知识提取、压缩、Dream/Distill
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from craft.config import CONFIG_DIR

logger = logging.getLogger(__name__)

SKILL_DB = CONFIG_DIR / "skills.json"


class SkillStep:
    def __init__(self, name: str, agent_id: str = "build", prompt: str = "",
                 input_key: str = "", output_key: str = "",
                 max_tokens: int = 4096, temperature: float = 0.3):
        self.name = name
        self.agent_id = agent_id
        self.prompt = prompt
        self.input_key = input_key
        self.output_key = output_key
        self.max_tokens = max_tokens
        self.temperature = temperature


class Skill:
    def __init__(self, name: str, description: str = "", version: str = "1.0.0"):
        self.id = f"skill_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.description = description
        self.version = version
        self.steps: list[SkillStep] = []
        self.input_schema: dict = {}
        self.output_schema: dict = {}
        self.author: str = ""
        self.tags: list[str] = []
        self.created_at = time.time()

    def add_step(self, step: SkillStep):
        self.steps.append(step)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "version": self.version, "steps": [s.__dict__ for s in self.steps],
            "author": self.author, "tags": self.tags,
            "created_at": self.created_at,
        }


class SkillManager:
    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._load()
        self._register_builtin()

    def _load(self):
        try:
            if SKILL_DB.exists():
                data = json.loads(SKILL_DB.read_text())
                for item in data:
                    skill = Skill("")
                    skill.__dict__.update(item)
                    self._skills[skill.id] = skill
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SKILL_DB.write_text(json.dumps(
            [s.to_dict() for s in self._skills.values()], indent=2, default=str
        ))

    def _register_builtin(self):
        """内置 Skill：Dream（知识提取）、Distill（知识压缩）"""
        dream = Skill("dream", "从对话中提取知识存入记忆", version="1.0.0")
        dream.add_step(SkillStep("extract", "build", "从以下对话中提取关键知识、决策和洞见，以简洁的格式输出。"))
        dream.add_step(SkillStep("store", "build", "将提取的知识存入记忆系统。"))
        self.add(dream, builtin=True)

        distill = Skill("distill", "压缩和重组知识", version="1.0.0")
        distill.add_step(SkillStep("analyze", "plan", "分析以下内容，提取核心概念和关系。"))
        distill.add_step(SkillStep("synthesize", "build", "将分析结果压缩为清晰的摘要。"))
        distill.tags = ["knowledge", "compress"]
        self.add(distill, builtin=True)

        code_review = Skill("code-review", "代码审查", version="1.0.0")
        code_review.add_step(SkillStep("analyze", "plan", "审查以下代码，指出问题。"))
        code_review.add_step(SkillStep("fix", "build", "修复发现的问题。"))
        code_review.tags = ["code", "review"]
        self.add(code_review, builtin=True)

    def add(self, skill: Skill, builtin: bool = False) -> str:
        self._skills[skill.id] = skill
        if not builtin:
            self._save()
        return skill.id

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list(self, tag: str | None = None) -> list[dict]:
        skills = self._skills.values()
        if tag:
            skills = [s for s in skills if tag in s.tags]
        return [s.to_dict() for s in skills]

    def delete(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            del self._skills[skill_id]
            self._save()
            return True
        return False


skills = SkillManager()
