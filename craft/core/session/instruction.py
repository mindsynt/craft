"""Instruction file resolution — ported from instruction.ts.

Finds AGENTS.md / CLAUDE.md / CONTEXT.md files for the system prompt.
"""

from __future__ import annotations

import os
from typing import Any


FILES = ["AGENTS.md", "CLAUDE.md", "CONTEXT.md"]


class InstructionManager:
    """Resolves instruction files from the project tree and global config."""

    def __init__(self):
        self._claims: dict[str, set[str]] = {}  # message_id -> set of file paths

    def find(self, directory: str, files: list[str] | None = None) -> str | None:
        """Find the first instruction file in a directory."""
        check = files or FILES
        for f in check:
            fp = os.path.join(directory, f)
            if os.path.isfile(fp):
                return fp
        return None

    def find_up(self, filename: str, start_dir: str, root_dir: str | None = None) -> list[str]:
        """Find a file walking up the directory tree."""
        results: list[str] = []
        current = os.path.abspath(start_dir)
        root = os.path.abspath(root_dir) if root_dir else os.path.sep
        while current.startswith(root) and os.path.isdir(current):
            fp = os.path.join(current, filename)
            if os.path.isfile(fp):
                results.append(fp)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return results

    def read_file(self, filepath: str) -> str:
        """Read a file, returning empty string on error."""
        try:
            with open(filepath) as f:
                return f.read()
        except (FileNotFoundError, OSError):
            return ""

    def read_files(self, paths: list[str]) -> list[str]:
        """Read multiple files concurrently (simplified: sequential)."""
        return [self.read_file(p) for p in paths]

    def clear_claim(self, message_id: str) -> None:
        self._claims.pop(message_id, None)

    def has_claim(self, message_id: str, path: str) -> bool:
        return message_id in self._claims and path in self._claims[message_id]

    def add_claim(self, message_id: str, path: str) -> None:
        self._claims.setdefault(message_id, set()).add(path)

    def system_paths(
        self,
        config: dict[str, Any],
        worktree: str,
        home_dir: str | None = None,
    ) -> set[str]:
        """Resolve all system instruction paths."""
        paths: set[str] = set()
        if home_dir is None:
            home_dir = os.path.expanduser("~")

        # Project-level AGENTS.md
        agents = self.find_up("AGENTS.md", worktree)
        if agents:
            for a in agents:
                paths.add(os.path.abspath(a))
            # Also check CLAUDE.md if AGENTS.md is small
            agents_content = "".join(self.read_files(agents)).strip()
            if len(agents_content) < 500:
                claude = self.find_up("CLAUDE.md", worktree)
                for c in claude:
                    paths.add(os.path.abspath(c))
        else:
            for file in FILES:
                if file == "AGENTS.md":
                    continue
                matches = self.find_up(file, worktree)
                if matches:
                    for m in matches:
                        paths.add(os.path.abspath(m))
                    break

        # Global: ~/.config/craft/AGENTS.md
        global_path = os.path.join(os.path.dirname(os.path.dirname(worktree)), "AGENTS.md")
        config_dir = os.path.join(home_dir, ".config", "craft")
        cfg_agents = os.path.join(config_dir, "AGENTS.md")
        for p in [cfg_agents]:
            if os.path.isfile(p):
                paths.add(os.path.abspath(p))

        claude_path = os.path.join(home_dir, ".claude", "CLAUDE.md")
        if os.path.isfile(claude_path):
            paths.add(os.path.abspath(claude_path))

        # Config instructions
        for raw in config.get("instructions", []):
            if raw.startswith("http://") or raw.startswith("https://"):
                continue
            instruction_path = raw.replace("~/", home_dir + "/", 1) if raw.startswith("~/") else raw
            if os.path.isabs(instruction_path):
                if os.path.isfile(instruction_path):
                    paths.add(os.path.abspath(instruction_path))
            else:
                matches = self.find_up(instruction_path, worktree)
                for m in matches:
                    paths.add(os.path.abspath(m))

        return paths


instruction_manager = InstructionManager()
