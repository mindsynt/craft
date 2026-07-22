"""
权限系统 — 移植自 MiMo-Code packages/opencode/src/permission.ts
基于规则的权限：允许列表 + 拒绝列表 + 硬限制
"""

from __future__ import annotations


from pydantic import BaseModel, Field


class PermissionRule:
    """单条权限规则"""
    ALLOW = "allow"
    DENY = "deny"

    def __init__(self, action: str, target: str = "*", reason: str = ""):
        self.action = action  # allow / deny
        self.target = target  # 工具名或模式
        self.reason = reason

    def matches(self, tool_name: str) -> bool:
        """检查是否匹配此规则"""
        if self.target == "*":
            return True
        if self.target.endswith("*"):
            return tool_name.startswith(self.target[:-1])
        return tool_name == self.target


class Ruleset(BaseModel):
    """权限规则集"""
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)

    def evaluate(self, tool_name: str) -> bool:
        """评估工具是否允许使用"""
        for d in self.deny:
            rule = PermissionRule(PermissionRule.DENY, d)
            if rule.matches(tool_name):
                return False
        for a in self.allow:
            rule = PermissionRule(PermissionRule.ALLOW, a)
            if rule.matches(tool_name):
                return True
        # 默认：只有 allow 列表中有匹配才允许
        return len(self.allow) == 0  # 空列表 = 全部允许


def merge_rulesets(base: Ruleset, overlay: Ruleset | None, hard: Ruleset | None = None) -> Ruleset:
    """合并权限规则：base + overlay，然后追加 hard（不可覆盖）"""
    result = Ruleset(
        allow=list(base.allow),
        deny=list(base.deny),
    )
    if overlay:
        result.allow.extend(overlay.allow)
        result.deny.extend(overlay.deny)
    if hard:
        # hard 规则强制追加（对应 agent.hardPermission）
        result.deny.extend(hard.deny)
        result.allow.extend(hard.allow)
    return result
