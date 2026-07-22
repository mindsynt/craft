import platform

from .process import run_process


async def extract_zip(zip_path: str, dest_dir: str):
    """解压 ZIP — 移植自 archive.ts extractZip"""
    if platform.system() == "Windows":
        import subprocess
        cmd = (
            f'$global:ProgressPreference = "SilentlyContinue"; '
            f'Expand-Archive -Path "{zip_path}" -DestinationPath "{dest_dir}" -Force'
        )
        await run_process(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd])
    else:
        await run_process(["unzip", "-o", "-q", zip_path, "-d", dest_dir])
