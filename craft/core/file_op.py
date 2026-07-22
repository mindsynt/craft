"""
文件操作 — 移植自 packages/opencode/src/file/
文件读写、监控、搜索
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import time
from pathlib import Path


class FileInfo:
    def __init__(self, path: str):
        self.path = path
        self.name = Path(path).name
        self.ext = Path(path).suffix
        self.size = 0
        self.mtime = 0
        self.is_dir = False
        self.is_binary = False
        self.mime = ""
        self.hash_val = ""
        self._stat()

    def _stat(self):
        try:
            s = os.stat(self.path)
            self.size = s.st_size
            self.mtime = s.st_mtime
            self.is_dir = os.path.isdir(self.path)
            self.mime = mimetypes.guess_type(self.path)[0] or "application/octet-stream"
            self.is_binary = self._check_binary()
        except Exception:
            pass

    def _check_binary(self) -> bool:
        try:
            with open(self.path, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except Exception:
            return True

    def compute_hash(self) -> str:
        try:
            h = hashlib.sha256()
            with open(self.path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            self.hash_val = h.hexdigest()[:16]
            return self.hash_val
        except Exception:
            return ""


class FileWatcher:
    def __init__(self):
        self._watches: dict[str, float] = {}

    def watch(self, path: str) -> str:
        wid = f"watch_{hash(path) % 100000:05d}"
        self._watches[wid] = time.time()
        return wid

    def changed(self, watch_id: str, path: str) -> bool:
        try:
            cur = os.path.getmtime(path)
            last = self._watches.get(watch_id, 0)
            return cur > last
        except Exception:
            return False

    def remove(self, watch_id: str):
        self._watches.pop(watch_id, None)


class FileManager:
    @staticmethod
    def read(path: str, encoding: str = "utf-8") -> str | None:
        try:
            return Path(path).read_text(encoding=encoding)
        except Exception:
            return None

    @staticmethod
    def write(path: str, content: str, encoding: str = "utf-8") -> bool:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding=encoding)
            return True
        except Exception:
            return False

    @staticmethod
    def exists(path: str) -> bool:
        return Path(path).exists()

    @staticmethod
    def delete(path: str) -> bool:
        try:
            p = Path(path)
            if p.is_dir() and not p.is_symlink():
                import shutil
                shutil.rmtree(p)
            else:
                p.unlink()
            return True
        except Exception:
            return False

    @staticmethod
    def list_dir(path: str, pattern: str = "*") -> list[str]:
        try:
            return [str(p) for p in Path(path).glob(pattern) if p.exists()]
        except Exception:
            return []

    @staticmethod
    def info(path: str) -> FileInfo | None:
        try:
            return FileInfo(path)
        except Exception:
            return None


fm = FileManager()
