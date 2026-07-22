from pathlib import Path
import shutil


class FileSystem:
    """文件系统操作"""

    @staticmethod
    async def read_text(path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception:
            return None

    @staticmethod
    async def write_text(path: str, content: str) -> bool:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    @staticmethod
    async def exists(path: str) -> bool:
        return Path(path).exists()

    @staticmethod
    async def remove(path: str) -> bool:
        try:
            p = Path(path)
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            return True
        except Exception:
            return False

    @staticmethod
    async def copy(src: str, dst: str) -> bool:
        try:
            shutil.copy2(src, dst)
            return True
        except Exception:
            return False

    @staticmethod
    async def list_dir(path: str, pattern: str | None = None) -> list[str]:
        try:
            p = Path(path)
            if pattern:
                return [str(f) for f in p.glob(pattern)]
            return [str(f) for f in p.iterdir()]
        except Exception:
            return []

    @staticmethod
    async def mkdir(path: str) -> bool:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    @staticmethod
    async def is_dir(path: str) -> bool:
        """检查是否为目录 — 移植自 filesystem.ts isDir"""
        try:
            return Path(path).is_dir()
        except Exception:
            return False

    @staticmethod
    async def size(path: str) -> int:
        """获取文件大小 — 移植自 filesystem.ts size"""
        try:
            return Path(path).stat().st_size
        except Exception:
            return 0

    @staticmethod
    def contains(parent: str, child: str) -> bool:
        """检查父路径是否包含子路径 — 移植自 filesystem.ts contains"""
        try:
            rel = Path(child).relative_to(parent)
            return not str(rel).startswith("..")
        except ValueError:
            return False

    @staticmethod
    async def find_up(targets: str | list[str], start: str, stop: str | None = None) -> list[str]:
        """向上查找文件 — 移植自 filesystem.ts findUp"""
        if isinstance(targets, str):
            targets = [targets]
        dirs = []
        current = start
        while True:
            dirs.append(current)
            if stop is not None and current == stop:
                break
            parent = str(Path(current).parent)
            if parent == current:
                break
            current = parent
        result = []
        for d in dirs:
            for t in targets:
                candidate = str(Path(d) / t)
                if await FileSystem.exists(candidate):
                    result.append(candidate)
        return result
