import subprocess


async def which(cmd: str) -> str | None:
    """查找可执行文件路径"""
    try:
        r = subprocess.run(["which", cmd], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None
