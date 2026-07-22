"""Checkpoint path utilities — ported from checkpoint-paths.ts."""

import os
import shutil


def meta_dir(session_id: str, data_root: str | None = None) -> str:
    """Session memory root. Houses checkpoints, task narratives, etc."""
    root = data_root or os.path.join(os.path.expanduser("~"), ".craft", "data")
    return os.path.join(root, "memory", "sessions", session_id)


def checkpoint_path(session_id: str, data_root: str | None = None) -> str:
    """v5 single-file checkpoint at <sid>/checkpoint.md."""
    return os.path.join(meta_dir(session_id, data_root), "checkpoint.md")


def memory_path(project_id: str, data_root: str | None = None) -> str:
    """Per-project memory file at <data>/memory/projects/<pid>/MEMORY.md."""
    root = data_root or os.path.join(os.path.expanduser("~"), ".craft", "data")
    return os.path.join(root, "memory", "projects", project_id, "MEMORY.md")


def global_memory_path(data_root: str | None = None) -> str:
    """Global memory file at <data>/memory/global/MEMORY.md."""
    root = data_root or os.path.join(os.path.expanduser("~"), ".craft", "data")
    return os.path.join(root, "memory", "global", "MEMORY.md")


def notes_path(session_id: str, data_root: str | None = None) -> str:
    """Session-scoped notes file at <sid>/notes.md."""
    return os.path.join(meta_dir(session_id, data_root), "notes.md")


def tasks_dir(session_id: str, data_root: str | None = None) -> str:
    """Per-session tasks directory at <sid>/tasks/."""
    return os.path.join(meta_dir(session_id, data_root), "tasks")


def progress_path(session_id: str, task_id: str, data_root: str | None = None) -> str:
    """Per-task progress journal at <sid>/tasks/<TID>/progress.md."""
    return os.path.join(tasks_dir(session_id, data_root), task_id, "progress.md")


def migrate_project_memory(project_id: str, data_root: str | None = None) -> bool:
    """Rename legacy lowercase memory.md to MEMORY.md. Idempotent.
    Returns True if a rename occurred, False otherwise.
    """
    upper = memory_path(project_id, data_root)
    lower = os.path.join(os.path.dirname(upper), "memory.md")
    if os.path.exists(upper):
        return False
    if os.path.exists(lower):
        shutil.move(lower, upper)
        return True
    return False
