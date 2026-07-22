"""
文件操作 — 移植自 packages/opencode/src/file/
文件读写、监控、搜索、忽略规则、保护路径、文件类型检测、ripgrep 集成
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from craft.core.bus import define_event


# ── 事件 ────────────────────────────────────────────────────

FileEditedEvent = define_event("file.edited", {"file": str})
FileWatcherUpdatedEvent = define_event("file.watcher.updated", {
    "file": str,
    "event": str,  # "add" | "change" | "unlink"
})


# ── 文件类型检测 ────────────────────────────────────────────
# 对应 TS file/index.ts 中的 binary/image/text 集合

BINARY_EXTENSIONS: set[str] = {
    "exe", "dll", "pdb", "bin", "so", "dylib", "o", "a", "lib",
    "wav", "mp3", "ogg", "oga", "ogv", "ogx", "flac", "aac",
    "wma", "m4a", "weba",
    "mp4", "avi", "mov", "wmv", "flv", "webm", "mkv",
    "zip", "tar", "gz", "gzip", "bz", "bz2", "bzip", "bzip2",
    "7z", "rar", "xz", "lz", "z",
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "dmg", "iso", "img", "vmdk",
    "ttf", "otf", "woff", "woff2", "eot",
    "sqlite", "db", "mdb",
    "apk", "ipa", "aab", "xapk",
    "app", "pkg", "deb", "rpm", "snap", "flatpak", "appimage",
    "msi", "msp",
    "jar", "war", "ear", "class", "kotlin_module",
    "dex", "vdex", "odex", "oat", "art",
    "wasm", "bc", "ll", "s", "ko", "sys", "drv", "efi", "rom", "com",
}

IMAGE_EXTENSIONS: set[str] = {
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "ico",
    "tif", "tiff", "svg", "svgz", "avif", "apng", "jxl",
    "heic", "heif", "raw", "cr2", "nef", "arw", "dng",
    "orf", "raf", "pef", "x3f",
}

TEXT_EXTENSIONS: set[str] = {
    "ts", "tsx", "mts", "cts", "mtsx", "ctsx",
    "js", "jsx", "mjs", "cjs",
    "sh", "bash", "zsh", "fish", "ps1", "psm1", "cmd", "bat",
    "json", "jsonc", "json5",
    "yaml", "yml", "toml",
    "md", "mdx", "txt", "xml", "html", "htm",
    "css", "scss", "sass", "less",
    "graphql", "gql", "sql",
    "ini", "cfg", "conf", "env",
    "py", "pyi", "rb", "go", "rs", "zig",
    "java", "kt", "kts", "swift", "m", "h",
    "c", "cc", "cpp", "cxx", "hpp", "hxx",
    "lua", "elm", "ex", "exs", "clj", "cljs",
}

TEXT_NAMES: set[str] = {
    "dockerfile", "makefile", ".gitignore", ".gitattributes",
    ".editorconfig", ".npmrc", ".nvmrc", ".prettierrc",
    ".eslintrc",
}


def _ext(file: str) -> str:
    return Path(file).suffix.lower().lstrip(".")


def _name(file: str) -> str:
    return Path(file).name.lower()


def is_binary_by_extension(file: str) -> bool:
    return _ext(file) in BINARY_EXTENSIONS


def is_image_by_extension(file: str) -> bool:
    return _ext(file) in IMAGE_EXTENSIONS


def is_text_by_extension(file: str) -> bool:
    return _ext(file) in TEXT_EXTENSIONS


def is_text_by_name(file: str) -> bool:
    return _name(file) in TEXT_NAMES


def is_binary_content(path: str) -> bool:
    """通过内容检测是否二进制文件"""
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return True


def get_mime_type(file: str) -> str:
    """获取 MIME 类型"""
    mime_map: dict[str, str] = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp",
        "ico": "image/x-icon", "tif": "image/tiff", "tiff": "image/tiff",
        "svg": "image/svg+xml", "svgz": "image/svg+xml",
        "avif": "image/avif", "apng": "image/apng",
        "jxl": "image/jxl", "heic": "image/heic", "heif": "image/heif",
    }
    return mime_map.get(_ext(file)) or mimetypes.guess_type(file)[0] or "application/octet-stream"


def should_encode(mime_type: str) -> bool:
    """判断是否需要 Base64 编码"""
    t = mime_type.lower()
    if not t or t.startswith("text/") or "charset=" in t:
        return False
    top = t.split("/", 1)[0] if "/" in t else t
    return top in ("image", "audio", "video", "font", "model", "multipart")


def is_hidden(item: str) -> bool:
    """检查路径是否包含隐藏文件/目录"""
    normalized = item.replace("\\", "/").rstrip("/")
    return any(part.startswith(".") and len(part) > 1 for part in normalized.split("/"))


def sort_hidden_last(items: list[str], prefer_hidden: bool = False) -> list[str]:
    """排序：隐藏文件排最后"""
    if prefer_hidden:
        return items
    visible: list[str] = []
    hidden_items: list[str] = []
    for item in items:
        if is_hidden(item):
            hidden_items.append(item)
        else:
            visible.append(item)
    return visible + hidden_items


# ── 文件忽略规则 (ignore.ts) ────────────────────────────────

IGNORE_FOLDERS: set[str] = {
    "node_modules", "bower_components", ".pnpm-store", "vendor",
    ".npm", "dist", "build", "out", ".next", "target",
    "bin", "obj", ".git", ".svn", ".hg",
    ".vscode", ".idea", ".turbo", ".output", ".sst",
    ".cache", ".webkit-cache",
    "__pycache__", ".pytest_cache", "mypy_cache",
    ".history", ".gradle",
}

IGNORE_GLOB_PATTERNS: list[str] = [
    "**/*.swp", "**/*.swo",
    "**/*.pyc",
    "**/.DS_Store", "**/Thumbs.db",
    "**/logs/**", "**/tmp/**", "**/temp/**",
    "**/*.log",
    "**/coverage/**", "**/.nyc_output/**",
]


def is_ignored(filepath: str, extra_patterns: list[str] | None = None,
               whitelist: list[str] | None = None) -> bool:
    """检查文件是否应被忽略（类似 TS FileIgnore.match）

    Args:
        filepath: 文件路径
        extra_patterns: 额外忽略模式
        whitelist: 白名单模式
    """
    if whitelist:
        import fnmatch
        for pattern in whitelist:
            if fnmatch.fnmatch(filepath, pattern):
                return False

    parts = filepath.replace("\\", "/").split("/")
    for part in parts:
        if part in IGNORE_FOLDERS:
            return True

    import fnmatch
    all_patterns = list(IGNORE_GLOB_PATTERNS) + (extra_patterns or [])
    for pattern in all_patterns:
        # 简化 glob 匹配
        regex = fnmatch.translate(pattern)
        if re.match(regex, filepath, re.IGNORECASE):
            return True

    return False


# ── 保护路径 (protected.ts) ────────────────────────────────

def get_protected_home_names() -> set[str]:
    """获取受保护的 HOME 目录名列表"""
    import platform
    system = platform.system()
    if system == "Darwin":
        return {"Music", "Pictures", "Movies", "Downloads", "Desktop",
                "Documents", "Public", "Applications", "Library"}
    if system == "Windows":
        return {"AppData", "Downloads", "Desktop", "Documents", "Pictures",
                "Music", "Videos", "OneDrive"}
    return set()


def get_protected_paths() -> list[str]:
    """获取绝对保护路径列表"""
    import platform
    home = os.path.expanduser("~")
    system = platform.system()
    paths: list[str] = []
    if system == "Darwin":
        for name in get_protected_home_names():
            paths.append(os.path.join(home, name))
        paths.extend([
            os.path.join(home, "Library", n) for n in [
                "Application Support/AddressBook", "Calendars", "Mail",
                "Messages", "Safari", "Cookies",
                "Application Support/com.apple.TCC",
                "PersonalizationPortrait", "Metadata/CoreSpotlight",
                "Suggestions",
            ]
        ])
        paths.extend(["/.DocumentRevisions-V100", "/.Spotlight-V100",
                       "/.Trashes", "/.fseventsd"])
    elif system == "Windows":
        for name in get_protected_home_names():
            paths.append(os.path.join(home, name))
    return paths


# ── Ripgrep 集成 (ripgrep.ts) ────────────────────────────────

RIPGREP_VERSION = "15.1.0"

RIPGREP_PLATFORMS: dict[str, dict[str, str]] = {
    "arm64-darwin": {"platform": "aarch64-apple-darwin", "extension": "tar.gz"},
    "arm64-linux": {"platform": "aarch64-unknown-linux-gnu", "extension": "tar.gz"},
    "x64-darwin": {"platform": "x86_64-apple-darwin", "extension": "tar.gz"},
    "x64-linux": {"platform": "x86_64-unknown-linux-musl", "extension": "tar.gz"},
    "arm64-win32": {"platform": "aarch64-pc-windows-msvc", "extension": "zip"},
    "ia32-win32": {"platform": "i686-pc-windows-msvc", "extension": "zip"},
    "x64-win32": {"platform": "x86_64-pc-windows-msvc", "extension": "zip"},
}


class RipgrepService:
    """Ripgrep 搜索服务

    支持文件列表、树状目录、内容搜索。
    """

    def __init__(self):
        self._binary: str | None = None

    def _find_binary(self) -> str | None:
        """查找 rg 二进制"""
        # 系统路径
        rg = os.popen("which rg 2>/dev/null || where rg 2>nul").read().strip()
        if rg and os.path.isfile(rg):
            return rg
        return None

    @property
    def binary(self) -> str | None:
        if self._binary is None:
            self._binary = self._find_binary()
        return self._binary

    @property
    def available(self) -> bool:
        return self.binary is not None

    def _run(self, args: list[str], cwd: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
        if not self.binary:
            return subprocess.CompletedProcess(args, 1, "", "ripgrep not available")
        try:
            return subprocess.run(
                [self.binary] + args,
                capture_output=True, text=True, timeout=timeout,
                cwd=cwd,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return subprocess.CompletedProcess(args, 1, "", "")

    def files(self, cwd: str, glob: list[str] | None = None,
              hidden: bool = True, follow: bool = False,
              max_depth: int | None = None) -> list[str]:
        """列出文件（对应 TS Ripgrep.files）"""
        args = ["--no-config", "--files", "--glob=!.git/*"]
        if follow:
            args.append("--follow")
        if hidden is not False:
            args.append("--hidden")
        if hidden is False:
            args.append("--glob=!.*")
        if max_depth is not None:
            args.append(f"--max-depth={max_depth}")
        if glob:
            for g in glob:
                args.append(f"--glob={g}")
        args.append(".")

        r = self._run(args, cwd=cwd)
        if r.returncode not in (0, 1):
            return []
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]

    def search(self, pattern: str, cwd: str, glob: list[str] | None = None,
               limit: int | None = None, file: list[str] | None = None,
               follow: bool = False) -> dict:
        """搜索内容（对应 TS Ripgrep.search）"""
        args = ["--no-config", "--json", "--hidden", "--glob=!.git/*", "--no-messages"]
        if follow:
            args.append("--follow")
        if glob:
            for g in glob:
                args.append(f"--glob={g}")
        if limit:
            args.append(f"--max-count={limit}")
        args.extend(["--", pattern])
        args.extend(file or ["."])

        r = self._run(args, cwd=cwd)
        if r.returncode not in (0, 1, 2):
            return {"items": [], "partial": False}

        items: list[dict] = []
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            try:
                import json
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data.get("data", {})
                    items.append({
                        "path": {"text": match_data.get("path", {}).get("text", "")},
                        "lines": {"text": match_data.get("lines", {}).get("text", "")},
                        "line_number": match_data.get("line_number", 0),
                        "absolute_offset": match_data.get("absolute_offset", 0),
                        "submatches": match_data.get("submatches", []),
                    })
            except (json.JSONDecodeError, KeyError):
                continue

        return {
            "items": items,
            "partial": r.returncode == 2,
        }

    def tree(self, cwd: str, limit: int | None = None) -> str:
        """生成目录树（对应 TS Ripgrep.tree）"""
        file_list = self.files(cwd)
        # 过滤系统目录
        file_list = [f for f in file_list if ".mimocode" not in f and ".craft" not in f]

        # 构建树
        tree: dict[str, set[str]] = {}
        for file_path in file_list:
            parts = Path(file_path).parts
            if len(parts) < 2:
                continue
            for i in range(1, len(parts)):
                parent = str(Path(*parts[:i]))
                child = parts[i] if i < len(parts) else ""
                tree.setdefault(parent, set()).add(child)

        total = sum(len(v) for v in tree.values())
        used_limit = limit or total
        lines: list[str] = []
        used = 0

        # BFS 输出
        queue: list[str] = []
        for key in sorted(tree.keys()):
            for child in sorted(tree[key]):
                if used >= used_limit:
                    break
                lines.append(f"{key}/{child}")
                used += 1

        if total > used:
            lines.append(f"[{total - used} truncated]")

        return "\n".join(lines)


ripgrep = RipgrepService()


# ── FileInfo ──────────────────────────────────────────────────

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
            self.mime = get_mime_type(self.path)
            self.is_binary = is_binary_content(self.path) or is_binary_by_extension(self.path)
        except Exception:
            pass

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


# ── FileWatcher ──────────────────────────────────────────────
# 对应 TS file/watcher.ts

class FileWatcher:
    """文件变更监视器

    使用 stat 轮询检测变更（简化版，对应 TS 的 @parcel/watcher 方案）
    """

    def __init__(self):
        self._watches: dict[str, float] = {}

    def watch(self, path: str) -> str:
        wid = f"watch_{abs(hash(path)) % 100000:05d}"
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

    def poll(self, path: str, interval: float = 1.0) -> bool:
        """轮询检测文件变更 — 简单 mtime 比较"""
        wid = f"poll_{abs(hash(path)) % 100000:05d}"
        changed = self.changed(wid, path)
        if changed:
            self._watches[wid] = os.path.getmtime(path)
        return changed


# ── FileManager ─────────────────────────────────────────────

class FileManager:
    """文件管理器 — 包含读、写、搜索、类型检测"""

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

    @staticmethod
    def detect_type(file: str) -> str:
        """检测文件类型: "text" | "binary" | "image" """
        if is_image_by_extension(file):
            return "image"
        if is_binary_by_extension(file) or is_binary_content(file):
            return "binary"
        return "text"

    @staticmethod
    def read_content(file: str) -> dict:
        """读取文件内容（类似 TS File.read）

        Returns: {"type": "text"|"binary", "content": str, "mimeType": str, ...}
        """
        mime = get_mime_type(file)
        if should_encode(mime):
            # 二进制：返回 base64
            import base64
            try:
                with open(file, "rb") as f:
                    data = base64.b64encode(f.read()).decode("ascii")
                return {"type": "binary", "content": data, "mimeType": mime, "encoding": "base64"}
            except Exception:
                return {"type": "binary", "content": "", "mimeType": mime}
        else:
            try:
                content = Path(file).read_text(encoding="utf-8")
                return {"type": "text", "content": content, "mimeType": mime}
            except UnicodeDecodeError:
                # 尝试 binary fallback
                import base64
                try:
                    with open(file, "rb") as f:
                        data = base64.b64encode(f.read()).decode("ascii")
                    return {"type": "binary", "content": data, "mimeType": mime, "encoding": "base64"}
                except Exception:
                    return {"type": "binary", "content": "", "mimeType": mime}
            except Exception:
                return {"type": "text", "content": "", "mimeType": mime}


fm = FileManager()
