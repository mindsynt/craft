"""Question tool."""

from .registry import tool


@tool(name="question", description="向用户提问",
      parameters={
          "type": "object",
          "properties": {
              "questions": {
                  "type": "array",
                  "items": {
                      "type": "object",
                      "properties": {
                          "question": {"type": "string"},
                          "header": {"type": "string"},
                          "options": {
                              "type": "array",
                              "items": {
                                  "type": "object",
                                  "properties": {
                                      "label": {"type": "string"},
                                      "description": {"type": "string"},
                                  },
                              },
                          },
                      },
                      "required": ["question"],
                  },
              },
          },
          "required": ["questions"],
      })
async def question(questions: list[dict]) -> str:
    try:
        parts = []
        for q in questions:
            header = q.get("header", "问题")
            question_text = q.get("question", "")
            options = q.get("options", [])
            parts.append(f"## {header}")
            parts.append(question_text)
            for opt in options:
                desc = f" - {opt.get('description', '')}" if opt.get("description") else ""
                parts.append(f"  [{opt.get('label', '?')}]{desc}")
        return "\n".join(parts)
    except Exception as e:
        return f"[错误] {e}"
