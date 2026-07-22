"""Skill content rendering — 移植自 packages/opencode/src/tool/skill-content.ts

Renders skill information with its file listing for the skill_search tool.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any


SKILL_SEARCH_FILE_SAMPLE_LIMIT = int(
    os.environ.get("MIMOCODE_SKILL_SEARCH_FILE_SAMPLE_LIMIT", "20")
)


async def render_skill_content(
    name: str,
    content: str,
    location: str,
    list_files_fn=None,
) -> dict:
    """Render skill content with file listing.

    Args:
        name: Skill name.
        content: Skill markdown content.
        location: Path to the skill's directory or SKILL.md file.
        list_files_fn: Optional async callable that takes a directory path
                       and returns a list of file paths (relative). If None,
                       falls back to os.walk.

    Returns:
        Dict with "dir" (str) and "output" (str).
    """
    # Determine the base directory
    loc_path = pathlib.Path(location)
    if loc_path.is_file():
        skill_dir = str(loc_path.parent)
    elif loc_path.is_dir():
        skill_dir = location
    else:
        skill_dir = str(loc_path.parent) if loc_path.parent else location

    # List files
    files: list[str] = []
    if list_files_fn is not None:
        all_files = await list_files_fn(skill_dir)
        files = [f for f in all_files if "SKILL.md" not in f][:SKILL_SEARCH_FILE_SAMPLE_LIMIT]
    else:
        # Fallback: simple os.walk
        try:
            for dirpath, _dirnames, filenames in os.walk(skill_dir):
                for fn in filenames:
                    if "SKILL.md" in fn:
                        continue
                    full = os.path.join(dirpath, fn)
                    files.append(full)
                    if len(files) >= SKILL_SEARCH_FILE_SAMPLE_LIMIT:
                        break
                if len(files) >= SKILL_SEARCH_FILE_SAMPLE_LIMIT:
                    break
        except (OSError, FileNotFoundError):
            pass

    file_lines = "\n".join(f"<file>{f}</file>" for f in files) if files else ""

    output = "\n".join([
        f"<skill_content name=\"{name}\">",
        f"# Skill: {name}",
        "",
        content.strip(),
        "",
        f"Base directory for this skill: {pathlib.Path(skill_dir).as_uri()}",
        "Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.",
        "Note: file list is sampled.",
        "",
        "<skill_files>",
        file_lines,
        "</skill_files>",
        "</skill_content>",
    ])

    return {"dir": skill_dir, "output": output}
