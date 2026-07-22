"""Jupyter Notebook edit tool."""

import json
import os
import uuid

from .registry import tool
from .session_cwd import SessionCwd
from .utils import _resolve_path


@tool(name="notebook_edit", description="编辑 Jupyter Notebook (.ipynb) 文件",
      parameters={
          "type": "object",
          "properties": {
              "notebook_path": {"type": "string", "description": ".ipynb 文件的绝对路径"},
              "cell_id": {"type": "string", "description": "要操作的 cell 的 ID"},
              "new_source": {"type": "string", "description": "cell 的新内容"},
              "cell_type": {"type": "string", "enum": ["code", "markdown"],
                            "description": "cell 类型"},
              "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"],
                            "description": "操作模式(默认 replace)"},
          },
          "required": ["notebook_path"],
      })
async def notebook_edit(notebook_path: str, cell_id: str = "",
                        new_source: str = "", cell_type: str = "code",
                        edit_mode: str = "replace") -> str:
    try:
        filepath = _resolve_path(notebook_path)
        if not filepath.endswith(".ipynb"):
            return "[错误] notebook_path 必须是 .ipynb 文件"
        if not os.path.isfile(filepath):
            return f"[错误] 文件不存在: {filepath}"

        with open(filepath, "r", encoding="utf-8") as f:
            notebook = json.load(f)

        cells = notebook.get("cells", [])
        if not isinstance(cells, list):
            return "[错误] Notebook 格式无效: 缺少 cells 数组"

        # Backfill missing cell IDs
        existing_ids = {c.get("id", "") for c in cells if c.get("id")}
        for cell in cells:
            if not cell.get("id"):
                cid = uuid.uuid4().hex[:8]
                while cid in existing_ids:
                    cid = uuid.uuid4().hex[:8]
                cell["id"] = cid
                existing_ids.add(cid)

        def find_cell(ref: str) -> int:
            if ref.startswith("#"):
                try:
                    idx = int(ref[1:])
                    if 0 <= idx < len(cells):
                        return idx
                except ValueError:
                    pass
                return -1
            for i, c in enumerate(cells):
                if c.get("id") == ref:
                    return i
            return -1

        if edit_mode == "replace":
            idx = find_cell(cell_id)
            if idx == -1:
                return f"[错误] 未找到 cell: {cell_id}"
            target = cells[idx]
            target_type = cell_type or target.get("cell_type", "code")
            target["source"] = new_source.split("\n") if new_source else []
            target["cell_type"] = target_type
            label = f"替换 cell {target.get('id', idx)}"
        elif edit_mode == "delete":
            idx = find_cell(cell_id)
            if idx == -1:
                return f"[错误] 未找到 cell: {cell_id}"
            cells.pop(idx)
            label = f"删除 cell {cell_id}"
        elif edit_mode == "insert":
            new_cell = {
                "cell_type": cell_type or "code",
                "id": uuid.uuid4().hex[:8],
                "source": new_source.split("\n") if new_source else [],
                "metadata": {},
            }
            if new_cell["cell_type"] == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            if cell_id and find_cell(cell_id) >= 0:
                idx = find_cell(cell_id)
                cells.insert(idx + 1, new_cell)
                label = f"在 {cell_id} 后插入"
            else:
                cells.insert(0, new_cell)
                label = "在开头插入"
        else:
            return f"[错误] 未知编辑模式: {edit_mode}"

        notebook["cells"] = cells
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
            f.write("\n")

        return f"Notebook 已更新: {label} on {os.path.relpath(filepath, SessionCwd._project_dir)}"
    except Exception as e:
        return f"[错误] {e}"
