"""Read file/directory contents tool."""

import os

from .registry import RecoverableError, tool
from .session_cwd import SessionCwd
from .utils import _is_binary_file, _resolve_path


def _read_file_with_lines(filepath: str, offset: int = 1, limit: int = 2000,
                          max_line_length: int = 2000, max_bytes: int = 51200):
    """Read a file with line tracking (port of read.ts `lines` function)."""
    raw: list[str] = []
    byte_count = 0
    line_count = 0
    cut = False
    more = False

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for text in f:
            line_count += 1
            if line_count < offset:
                continue
            if len(raw) >= limit:
                more = True
                continue
            text = text.rstrip("\r\n")
            if len(text) > max_line_length:
                text = text[:max_line_length] + f"... (line truncated to {max_line_length} chars)"
            sz = len(text.encode("utf-8")) + (1 if raw else 0)
            if byte_count + sz > max_bytes:
                cut = True
                more = True
                break
            raw.append(text)
            byte_count += sz

    return {"raw": raw, "count": line_count, "cut": cut, "more": more, "offset": offset}


@tool(name="read_file", description="读取文件或目录内容",
      parameters={
          "type": "object",
          "properties": {
              "file_path": {"type": "string", "description": "文件或目录的绝对路径"},
              "offset": {"type": "integer", "description": "起始行号(1-indexed, 仅文件)"},
              "limit": {"type": "integer", "description": "最大读取行数(仅文件, 默认2000)"},
          },
          "required": ["file_path"],
      })
async def read_file(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    try:
        filepath = _resolve_path(file_path)
        if not os.path.exists(filepath):
            # Suggest similar files
            parent = os.path.dirname(filepath)
            base = os.path.basename(filepath)
            if os.path.isdir(parent):
                similar = [os.path.join(parent, f) for f in os.listdir(parent)
                           if base.lower() in f.lower() or f.lower() in base.lower()]
                if similar:
                    return f"文件不存在: {filepath}\n您是否要找:\n" + "\n".join(similar[:3])
            return f"[错误] 文件不存在: {filepath}"

        if os.path.isdir(filepath):
            entries = sorted(os.listdir(filepath))
            result = [f"<path>{filepath}</path>", "<type>directory</type>", "<entries>"]
            start = max(0, offset - 1)
            sliced = entries[start:start + limit]
            truncated = start + len(sliced) < len(entries)
            result.extend(sliced)
            if truncated:
                result.append(f"\n(显示 {len(sliced)} 个, 共 {len(entries)} 个条目)")
            else:
                result.append(f"\n({len(entries)} 个条目)")
            result.append("</entries>")
            return "\n".join(result)

        # File: check binary
        if _is_binary_file(filepath):
            return f"[错误] 无法读取二进制文件: {filepath}"

        # File: read with lines
        info = _read_file_with_lines(filepath, offset=offset, limit=limit)
        if info["count"] < info["offset"] and not (info["count"] == 0 and info["offset"] == 1):
            return f"[错误] 偏移量 {info['offset']} 超出了范围(文件共 {info['count']} 行)"

        lines_output = []
        for i, line in enumerate(info["raw"]):
            lines_output.append(f"{i + info['offset']}: {line}")

        result = [
            f"<path>{filepath}</path>",
            "<type>file</type>",
            "<content>",
            *lines_output,
        ]

        last = info["offset"] + len(info["raw"]) - 1
        next_line = last + 1
        if info["cut"]:
            result.append(f"\n(输出限制在 50KB. 显示行 {info['offset']}-{last}. 使用 offset={next_line} 继续)")
        elif info["more"]:
            result.append(f"\n(显示行 {info['offset']}-{last}, 共 {info['count']} 行. 使用 offset={next_line} 继续)")
        else:
            result.append(f"\n(文件结束 - 共 {info['count']} 行)")
        result.append("</content>")

        return "\n".join(result)
    except Exception as e:
        return f"[错误] {e}"
