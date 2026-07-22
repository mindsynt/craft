"""Truncation service for large tool outputs."""

import os
import re
import tempfile
import uuid
from typing import Any

MAX_TRUNCATE_LINES = 2000
MAX_TRUNCATE_BYTES = 50 * 1024
TRUNCATION_DIR = os.path.join(tempfile.gettempdir(), "craft_truncation")
ERROR_PATTERN = re.compile(r"error|exception|failed|fatal|traceback|panic|exit code", re.IGNORECASE)


class Truncate:
    """Truncation service for large tool outputs."""

    @staticmethod
    def ensure_dir() -> str:
        os.makedirs(TRUNCATION_DIR, exist_ok=True)
        return TRUNCATION_DIR

    @staticmethod
    def write(text: str) -> str:
        path = os.path.join(Truncate.ensure_dir(), f"tool_{uuid.uuid4().hex[:16]}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    @staticmethod
    def output(text: str, max_lines: int | None = None,
               max_bytes: int | None = None,
               direction: str = "head+tail") -> dict[str, Any]:
        max_lines = max_lines or MAX_TRUNCATE_LINES
        max_bytes = max_bytes or MAX_TRUNCATE_BYTES
        lines = text.split("\n")
        total_bytes = len(text.encode("utf-8"))

        if len(lines) <= max_lines and total_bytes <= max_bytes:
            return {"content": text, "truncated": False}

        if direction == "head+tail":
            tail_scan = text[-2048:] if len(text) > 2048 else text
            has_errors = bool(ERROR_PATTERN.search(tail_scan))

            if has_errors:
                head_max_lines = int(max_lines * 0.7)
                head_max_bytes = int(max_bytes * 0.7)
                tail_max_lines = max_lines - head_max_lines
                tail_max_bytes = max_bytes - head_max_bytes

                head_out: list[str] = []
                head_bytes = 0
                for line in lines:
                    sz = len(line.encode("utf-8")) + (1 if head_out else 0)
                    if head_bytes + sz > head_max_bytes or len(head_out) >= head_max_lines:
                        break
                    head_out.append(line)
                    head_bytes += sz

                tail_out: list[str] = []
                tail_bytes = 0
                for line in reversed(lines):
                    sz = len(line.encode("utf-8")) + (1 if tail_out else 0)
                    if tail_bytes + sz > tail_max_bytes or len(tail_out) >= tail_max_lines:
                        break
                    tail_out.insert(0, line)
                    tail_bytes += sz

                omitted = len(lines) - len(head_out) - len(tail_out)
                filepath = Truncate.write(text)
                return {
                    "content": f"{chr(10).join(head_out)}\n\n... {omitted} lines omitted — showing head and tail ...\n\n{chr(10).join(tail_out)}\n\nFull output saved to: {filepath}",
                    "truncated": True,
                    "outputPath": filepath,
                }

        # Head-only truncation (default fallback)
        out: list[str] = []
        byte_count = 0
        for line in lines:
            sz = len(line.encode("utf-8")) + (1 if out else 0)
            if byte_count + sz > max_bytes or len(out) >= max_lines:
                break
            out.append(line)
            byte_count += sz

        removed = len(lines) - len(out)
        filepath = Truncate.write(text)
        return {
            "content": f"{chr(10).join(out)}\n\n...{removed} lines truncated...\n\nFull output saved to: {filepath}",
            "truncated": True,
            "outputPath": filepath,
        }
