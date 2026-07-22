"""Skill tools — load and search skills."""

import json

from .registry import tool


@tool(name="skill", description="加载专业化技能(skill)获取领域特定指令",
      parameters={
          "type": "object",
          "properties": {
              "name": {"type": "string", "description": "技能名称"},
          },
          "required": ["name"],
      })
async def skill(name: str) -> str:
    try:
        from craft.core.skill import skills
        all_skills = skills.list()
        for s in all_skills:
            s_name = getattr(s, "name", str(s))
            if name.lower() in s_name.lower():
                return f"已加载技能: {s_name}\n\n详细内容请查看技能文档."
        return (
            f"未找到技能 \"{name}\". "
            f"可用技能: {', '.join(getattr(s, 'name', str(s)) for s in all_skills[:10])}"
        )
    except Exception as e:
        return f"[错误] {e}"


@tool(name="skill_search", description="搜索可用技能(BM25 相关性匹配)",
      parameters={
          "type": "object",
          "properties": {
              "query": {"type": "string", "description": "搜索查询(包含动作、输入、预期输出和受众)"},
          },
          "required": ["query"],
      })
async def skill_search(query: str) -> str:
    try:
        from craft.core.skill import skills
        all_skills = skills.list()
        query_lower = query.lower()

        # Simple keyword matching
        results = []
        for s in all_skills:
            s_name = getattr(s, "name", str(s)).lower()
            s_desc = getattr(s, "description", "").lower() if hasattr(s, "description") else ""
            if query_lower in s_name or any(w in s_name for w in query_lower.split()):
                results.append(s)

        if not results:
            return json.dumps({"status": "no_match", "results": [],
                               "loaded_skill_id": None})

        names = [getattr(r, "name", str(r)) for r in results]
        return json.dumps({"status": "matched", "results": names,
                           "loaded_skill_id": names[0] if results else None})
    except Exception as e:
        return f"[错误] {e}"
