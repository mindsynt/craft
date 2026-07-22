"""文件操作路由 — 移植自 routes/instance/file.ts

文件搜索、列表、读取、状态查询。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class FileRoutes:
    """文件路由处理器

    对应 TS FileRoutes
    """

    @staticmethod
    async def find_text(request: Any) -> Any:
        """GET /find

        使用 ripgrep 搜索文本。
        """
        pattern = ""
        if hasattr(request, "query_params"):
            pattern = request.query_params.get("pattern", "")

        if not pattern:
            return []

        cwd = os.getcwd()
        results = []

        try:
            import subprocess
            cmd = ["rg", "--no-heading", "--line-number", "--max-count", "10", pattern, cwd]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, cwd=cwd
            )
            for line in proc.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    results.append({
                        "path": os.path.relpath(parts[0], cwd) if os.path.isabs(parts[0]) else parts[0],
                        "line": int(parts[1]) if parts[1].isdigit() else 0,
                        "content": parts[2] if len(parts) > 2 else "",
                    })
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.warning("rg search failed", extra={"error": str(e)})

        return results

    @staticmethod
    async def find_files(request: Any) -> Any:
        """GET /find/file

        搜索文件。
        """
        query = ""
        dirs = True
        file_type = None
        limit = 10

        if hasattr(request, "query_params"):
            qp = request.query_params
            query = qp.get("query", "")
            dirs = qp.get("dirs", "true").lower() not in ("false", "0")
            file_type = qp.get("type")
            if qp.get("limit"):
                try:
                    limit = int(qp["limit"])
                except (ValueError, TypeError):
                    pass

        if not query:
            return []

        cwd = os.getcwd()
        results = []
        try:
            from pathlib import Path
            for p in Path(cwd).rglob(f"*{query}*"):
                if len(results) >= limit:
                    break
                if p.is_file() or (p.is_dir() and dirs):
                    if file_type and file_type == "file" and not p.is_file():
                        continue
                    if file_type and file_type == "directory" and not p.is_dir():
                        continue
                    results.append(str(p.relative_to(cwd)))
        except Exception as e:
            logger.warning("File search failed", extra={"error": str(e)})

        return results

    @staticmethod
    async def find_symbols(request: Any) -> Any:
        """GET /find/symbol

        搜索符号（LSP）。
        """
        # LSP workspace symbols not yet available; return empty
        return []

    @staticmethod
    async def list(request: Any) -> Any:
        """GET /file

        列出目录内容。
        """
        path = ""
        if hasattr(request, "query_params"):
            path = request.query_params.get("path", ".")

        cwd = os.getcwd()
        target = os.path.join(cwd, path) if not os.path.isabs(path) else path

        try:
            entries = []
            for entry in os.scandir(target):
                entries.append({
                    "name": entry.name,
                    "path": os.path.relpath(entry.path, cwd),
                    "type": "directory" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else 0,
                })
            entries.sort(key=lambda e: (e["type"] != "directory", e["name"]))
            return entries
        except FileNotFoundError:
            return {"error": "Directory not found", "status": 404}
        except PermissionError:
            return {"error": "Permission denied", "status": 403}

    @staticmethod
    async def read(request: Any) -> Any:
        """GET /file/content

        读取文件内容。
        """
        file_path = ""
        if hasattr(request, "query_params"):
            file_path = request.query_params.get("path", "")

        if not file_path:
            return {"error": "No path specified", "status": 400}

        cwd = os.getcwd()
        target = os.path.join(cwd, file_path) if not os.path.isabs(file_path) else file_path

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "path": file_path,
                "content": content,
                "size": len(content),
            }
        except FileNotFoundError:
            return {"error": "File not found", "status": 404}
        except PermissionError:
            return {"error": "Permission denied", "status": 403}
        except IsADirectoryError:
            return {"error": "Path is a directory", "status": 400}

    @staticmethod
    async def status(request: Any) -> Any:
        """GET /file/status

        获取文件 git 状态。
        """
        cwd = os.getcwd()
        results = []
        try:
            import subprocess
            proc = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10, cwd=cwd
            )
            for line in proc.stdout.splitlines():
                if len(line) > 3:
                    xy = line[:2]
                    path = line[3:]
                    results.append({
                        "path": path,
                        "status": _git_status_label(xy),
                        "working": " " not in xy or xy[1] != " ",
                        "staged": xy[0] != " ",
                    })
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.warning("git status failed", extra={"error": str(e)})
        return results


def _git_status_label(xy: str) -> str:
    """Convert git status code to label"""
    mapping = {
        "M ": "modified",
        " M": "modified",
        "A ": "added",
        " D": "deleted",
        "D ": "deleted",
        "R ": "renamed",
        "C ": "copied",
        "UU": "conflict",
        "??": "untracked",
        "!!": "ignored",
    }
    return mapping.get(xy, "modified")
