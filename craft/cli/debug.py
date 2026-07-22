"""CLI debug commands — 移植自 packages/opencode/src/cli/cmd/debug/
Ripgrep and Scrap debug utilities.
"""

from __future__ import annotations

import json
import subprocess
import sys

from craft.cli.cmd import CmdDef


RipgrepCommand = CmdDef(
    command="rg",
    describe="ripgrep debugging utilities",
)


async def rg_tree(cwd: str | None = None, limit: int | None = None) -> str:
    """Show file tree using ripgrep-like output."""
    cmd = ["find", cwd or "."]
    if limit:
        cmd = cmd + ["-maxdepth", str(min(limit, 5))]
    result = subprocess.run(
        ["find", cwd or ".", "-type", "f"],
        capture_output=True, text=True, timeout=30,
    )
    lines = result.stdout.strip().split("\n")
    if limit:
        lines = lines[:limit]
    return "\n".join(lines)


async def rg_files(cwd: str | None = None, glob_pattern: str | None = None, limit: int | None = None) -> list[str]:
    """List files using ripgrep-like pattern matching."""
    try:
        if glob_pattern:
            cmd = ["rg", "--files", "--glob", glob_pattern, cwd or "."]
        else:
            cmd = ["rg", "--files", cwd or "."]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().split("\n")
        if limit and len(lines) > limit:
            lines = lines[:limit]
        return lines
    except FileNotFoundError:
        # Fallback to find
        cmd = ["find", cwd or ".", "-type", "f"]
        if glob_pattern:
            cmd = cmd + ["-name", glob_pattern]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().split("\n")
        if limit and len(lines) > limit:
            lines = lines[:limit]
        return lines
    except subprocess.TimeoutExpired:
        return []


async def rg_search(
    pattern: str,
    cwd: str | None = None,
    glob: list[str] | None = None,
    limit: int | None = None,
) -> dict:
    """Search file contents using ripgrep."""
    import json as _json

    try:
        cmd = ["rg", "--json", pattern, cwd or "."]
        if glob:
            for g in glob:
                cmd.extend(["--glob", g])
        if limit:
            cmd.extend(["-m", str(limit)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        items = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                parsed = _json.loads(line)
                if parsed.get("type") == "match":
                    data = parsed.get("data", {})
                    items.append({
                        "path": data.get("path", {}).get("text", ""),
                        "line": data.get("line_number"),
                        "column": data.get("submatches", [{}])[0].get("start"),
                        "text": data.get("lines", {}).get("text", "").strip(),
                    })
            except _json.JSONDecodeError:
                pass

        return {"items": items, "total": len(items)}
    except FileNotFoundError:
        # Fallback to grep
        try:
            cmd = ["grep", "-rn", pattern, cwd or "."]
            if glob:
                for g in glob:
                    cmd.extend(["--include", g])
            if limit:
                cmd.extend(["-m", str(limit)])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            items = []
            for line in result.stdout.strip().split("\n")[:limit or 100]:
                if ":" in line:
                    parts = line.split(":", 2)
                    items.append({"file": parts[0], "line": parts[1], "text": parts[2] if len(parts) > 2 else ""})
            return {"items": items, "total": len(items)}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"items": [], "total": 0}
    except subprocess.TimeoutExpired:
        return {"items": [], "total": 0}


ScrapCommand = CmdDef(
    command="scrap",
    describe="list all known projects",
)


async def scrap_projects() -> list[dict]:
    """List all known projects from scrap/scan data."""
    from pathlib import Path
    import time

    projects = []
    home = Path.home()
    for git_dir in home.glob("**/.git"):
        project_dir = git_dir.parent
        projects.append({
            "path": str(project_dir),
            "name": project_dir.name,
            "vcs": "git",
            "scanned_at": time.time(),
        })
    return projects[:100]  # Limit to 100 projects
