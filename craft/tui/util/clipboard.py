"""
剪贴板操作 — 移植自 util/clipboard.ts

跨平台剪贴板读写：macOS (osascript/pngpaste)、Linux (wl-copy/xclip/xsel)、
Windows (PowerShell)、OSC 52 终端转义序列 (SSH 场景)。
"""

from __future__ import annotations

import asyncio
import base64
import os
import platform
import struct
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional


def _osc52_write(text: str) -> None:
    """通过 OSC 52 转义序列写入剪贴板（SSH / tmux 场景）"""
    if not sys.stdout.isatty():
        return
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    osc52 = f"\x1b]52;c;{b64}\x07"
    passthrough = os.environ.get("TMUX") or os.environ.get("STY")
    sequence = f"\x1bPtmux;\x1b{osc52}\x1b\\\\" if passthrough else osc52
    sys.stdout.write(sequence)
    sys.stdout.flush()


async def _read_darwin_clipboard_image() -> Optional[dict]:
    """读取 macOS 剪贴板图片（AppKit → PNG）"""
    dest = Path(tempfile.gettempdir()) / f"craft-clipboard-{int(time.time() * 1000)}.png"
    try:
        # 1) pngpaste
        pngpaste = await _which("pngpaste")
        if pngpaste:
            proc = await asyncio.create_subprocess_exec(
                pngpaste, str(dest),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await proc.wait()
            if code == 0 and dest.exists() and dest.stat().st_size > 0:
                data = base64.b64encode(dest.read_bytes()).decode("ascii")
                return {"data": data, "mime": "image/png"}

        # 2) JXA (AppKit NSImage → PNG)
        jxa = (
            "ObjC.import('AppKit');"
            "const pb = $.NSPasteboard.generalPasteboard;"
            "const img = $.NSImage.alloc.initWithPasteboard(pb);"
            "if (!img) { $.exit(1); }"
            "const tiff = img.TIFFRepresentation;"
            "if (!tiff) { $.exit(1); }"
            "const rep = $.NSBitmapImageRep.imageRepWithData(tiff);"
            "const png = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $());"
            "if (!png) { $.exit(1); }"
            f"png.writeToFileAtomically($('{dest}'), true);"
        )
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-l", "JavaScript", "-e", jxa,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        code = await proc.wait()
        if code == 0 and dest.exists() and dest.stat().st_size > 0:
            data = base64.b64encode(dest.read_bytes()).decode("ascii")
            return {"data": data, "mime": "image/png"}

        # 3) osascript PNGf / TIFF fallback
        def _dump_clipboard(clazz: str, out: Path) -> bytes:
            proc = asyncio.create_subprocess_exec(
                "osascript",
                "-e", f"set imageData to the clipboard as {clazz}",
                "-e", f'set fileRef to open for access POSIX file "{out}" with write permission',
                "-e", "set eof fileRef to 0",
                "-e", "write imageData to fileRef",
                "-e", "close access fileRef",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return proc

        proc = _dump_clipboard('"PNGf"', dest)
        code = await (await proc).wait()
        if code == 0 and dest.exists() and dest.stat().st_size > 0:
            data = base64.b64encode(dest.read_bytes()).decode("ascii")
            return {"data": data, "mime": "image/png"}

        tiff_file = dest.with_suffix(".tiff")
        try:
            proc = _dump_clipboard("«class TIFF»", tiff_file)
            code = await (await proc).wait()
            if code == 0 and tiff_file.exists() and tiff_file.stat().st_size > 0:
                await _run(["sips", "-s", "format", "png", str(tiff_file), "--out", str(dest)])
                if dest.exists() and dest.stat().st_size > 0:
                    data = base64.b64encode(dest.read_bytes()).decode("ascii")
                    return {"data": data, "mime": "image/png"}
        finally:
            tiff_file.unlink(missing_ok=True)

        return None
    finally:
        dest.unlink(missing_ok=True)


async def read() -> Optional[dict]:
    """读取剪贴板内容 — 先尝试图片，再回退到文本"""
    _os = platform.system().lower()

    if _os == "darwin":
        image = await _read_darwin_clipboard_image()
        if image:
            return image

    if _os == "windows":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$img = [System.Windows.Forms.Clipboard]::GetImage(); "
            "if ($img) { "
            "$ms = New-Object System.IO.MemoryStream; "
            "$img.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); "
            "[System.Convert]::ToBase64String($ms.ToArray()) }"
        )
        text = await _run_text([
            "powershell.exe", "-NonInteractive", "-NoProfile", "-command", script
        ])
        if text and text.strip():
            img_bytes = base64.b64decode(text.strip())
            if len(img_bytes) > 0:
                return {"data": base64.b64encode(img_bytes).decode("ascii"), "mime": "image/png"}

    if _os == "linux":
        wayland = await _run_binary(["wl-paste", "-t", "image/png"])
        if wayland and len(wayland) > 0:
            return {"data": base64.b64encode(wayland).decode("ascii"), "mime": "image/png"}

        x11 = await _run_binary(["xclip", "-selection", "clipboard", "-t", "image/png", "-o"])
        if x11 and len(x11) > 0:
            return {"data": base64.b64encode(x11).decode("ascii"), "mime": "image/png"}

    # Fallback to text clipboard
    import pyperclip  # optional
    try:
        text = pyperclip.paste()
        if text:
            return {"data": text, "mime": "text/plain"}
    except Exception:
        pass

    return None


def _get_copy_method() -> Optional[callable]:
    """检测系统剪贴板写入方法"""
    _os = platform.system().lower()
    import shutil

    if _os == "darwin" and shutil.which("osascript"):

        async def _osascript_copy(text: str):
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            await _run(["osascript", "-e", f'set the clipboard to "{escaped}"'])

        return _osascript_copy

    if _os == "linux":
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):

            async def _wl_copy(text: str):
                proc = await asyncio.create_subprocess_exec(
                    "wl-copy",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                proc.stdin.write(text.encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()
                await proc.wait()

            return _wl_copy

        if shutil.which("xclip"):

            async def _xclip_copy(text: str):
                proc = await asyncio.create_subprocess_exec(
                    "xclip", "-selection", "clipboard",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                proc.stdin.write(text.encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()
                await proc.wait()

            return _xclip_copy

    return None


async def copy(text: str):
    """写入剪贴板 — OSC 52 + 系统方法双写"""
    _osc52_write(text)
    method = _get_copy_method()
    if method:
        await method(text)


# ─── internal helpers ─────────────────────────

async def _which(cmd: str) -> Optional[str]:
    import shutil
    return shutil.which(cmd)


async def _run(args: list[str]) -> int:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await proc.wait()


async def _run_text(args: list[str]) -> Optional[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out.decode("utf-8", errors="replace") if out else None
    except Exception:
        return None


async def _run_binary(args: list[str]) -> Optional[bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out if out and len(out) > 0 else None
    except Exception:
        return None
