"""Apply unified diff patch tool."""

import os
import re
from typing import Any

from .registry import tool
from .session_cwd import SessionCwd
from .utils import _resolve_path


@tool(name="apply_patch", description="应用统一差异补丁(支持增/删/改文件)",
      parameters={
          "type": "object",
          "properties": {
              "patch_text": {"type": "string", "description": "完整的补丁文本(描述所有要做的更改)"},
          },
          "required": ["patch_text"],
      })
async def apply_patch(patch_text: str) -> str:
    """Apply a unified diff patch to files."""
    try:
        if not patch_text.strip():
            return "[错误] patch_text 不能为空"

        patch_lines = patch_text.split("\n")

        # Parse hunks from the patch text
        current_file = ""
        hunks: list[dict[str, Any]] = []
        current_hunk: dict[str, Any] | None = None

        for line in patch_lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                continue
            m = re.match(r"^@@ -(\d+),?\d* \+(\d+),?\d* @@", line)
            if m:
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {"old_start": int(m.group(1)),
                                "new_start": int(m.group(2)),
                                "lines": [], "type": "update"}
                continue
            if line.startswith("*** Begin Patch"):
                continue
            if line.startswith("*** End Patch"):
                continue
            m = re.match(r"^\*\*\* Update File: (.+)", line)
            if m:
                current_file = m.group(1).strip()
                continue
            m = re.match(r"^\*\*\* (Add|Delete) File: (.+)", line)
            if m:
                action = m.group(1).lower()
                if action == "add":
                    fn = m.group(2).strip()
                    hunks.append({"type": "add", "file": fn, "lines": []})
                    current_file = fn
                    current_hunk = None
                elif action == "delete":
                    fn = m.group(2).strip()
                    hunks.append({"type": "delete", "file": fn})
                    current_file = fn
                    current_hunk = None
                continue
            if current_hunk is not None:
                current_hunk["lines"].append(line)
            elif hunks and hunks[-1]["type"] == "add" and current_file:
                hunks[-1].setdefault("lines", []).append(line)

        if current_hunk:
            hunks.append(current_hunk)

        if not hunks:
            return "[错误] 补丁中未找到 hunk"

        file_changes: list[dict[str, Any]] = []

        for hunk in hunks:
            hunk_type = hunk.get("type", "update")
            file_path = _resolve_path(str(hunk.get("file", current_file)))

            if hunk_type == "add":
                new_content = "\n".join(hunk.get("lines", []))
                if new_content.strip():
                    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content + "\n")
                    file_changes.append({"file": file_path, "type": "add"})
                continue

            if hunk_type == "delete":
                if os.path.exists(file_path):
                    os.remove(file_path)
                    file_changes.append({"file": file_path, "type": "delete"})
                continue

            # Update
            if not os.path.isfile(file_path):
                return f"[错误] 文件不存在: {file_path}"

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            new_content_lines = content.split("\n")

            # Apply hunk lines
            add_lines: list[str] = []
            del_count = 0
            current_line = int(hunk.get("old_start", 1)) - 1

            for hline in hunk.get("lines", []):
                if hline.startswith("+"):
                    add_lines.append(hline[1:])
                elif hline.startswith("-"):
                    del_count += 1
                else:
                    # Context line or first addition
                    if add_lines and del_count == 0:
                        # Insert without deletion
                        insert_at = current_line
                        if insert_at >= len(content.split("\n")):
                            insert_at = len(content.split("\n"))
                        new_content_lines[insert_at:insert_at] = add_lines
                        current_line += len(add_lines)
                        add_lines = []
                    elif add_lines and del_count > 0:
                        # Replace
                        new_content_lines[current_line:current_line + del_count] = add_lines
                        current_line += len(add_lines)
                        add_lines = []
                        del_count = 0
                    else:
                        current_line += 1

            # Flush remaining
            if add_lines:
                if del_count > 0:
                    new_content_lines[current_line:current_line + del_count] = add_lines
                else:
                    new_content_lines[current_line:current_line] = add_lines

            new_content = "\n".join(new_content_lines)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            file_changes.append({"file": file_path, "type": "update"})

        if not file_changes:
            return "未做出任何更改(补丁为空)"

        lines = [f"成功. 更新了 {len(file_changes)} 个文件:"]
        for ch in file_changes:
            action_map = {"add": "A", "update": "M", "delete": "D"}
            prefix = action_map.get(str(ch.get("type", "")), "?")
            rel = os.path.relpath(str(ch["file"]), SessionCwd._project_dir)
            lines.append(f"  {prefix} {rel}")

        return "\n".join(lines)
    except Exception as e:
        return f"[错误] {e}"
