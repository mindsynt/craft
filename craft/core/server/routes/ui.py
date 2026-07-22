"""UI 路由 — 移植自 routes/ui.ts

静态 Web UI 文件服务。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
    "font-src 'self' data:; media-src 'self' data:; "
    "connect-src 'self' data:"
)


class UIRoutes:
    """UI 路由处理器

    对应 TS UIRoutes
    """

    @staticmethod
    async def serve_ui(request: Any) -> Any:
        """GET /*

        服务 Web UI 静态文件或返回错误。
        """
        # 检查是否有嵌入的 Web UI
        ui_disabled = os.environ.get("CRAFT_DISABLE_EMBEDDED_WEB_UI", "").lower() in ("1", "true")
        if ui_disabled:
            return type("Response", (), {
                "status": 503,
                "body": '{"error": "Web UI is temporarily unavailable."}',
                "headers": {"Content-Type": "application/json"},
                "content_type": "application/json",
            })()

        # Try to serve from web-ui directory
        web_ui_dir = os.environ.get("CRAFT_WEB_UI_DIR", "")
        if web_ui_dir and os.path.isdir(web_ui_dir):
            path = getattr(request, "path", "/")
            file_path = os.path.join(web_ui_dir, path.lstrip("/"))
            if not file_path.startswith(os.path.abspath(web_ui_dir)):
                # Prevent directory traversal
                return type("Response", (), {
                    "status": 404,
                    "body": '{"error": "Not Found"}',
                    "headers": {"Content-Type": "application/json"},
                    "content_type": "application/json",
                })()

            if os.path.isfile(file_path):
                try:
                    with open(file_path, "rb") as f:
                        content = f.read()
                    mime = _guess_mime(file_path)
                    headers = {"Content-Type": mime}
                    if mime.startswith("text/html"):
                        headers["Content-Security-Policy"] = DEFAULT_CSP
                    return type("Response", (), {
                        "status": 200,
                        "body": content,
                        "headers": headers,
                        "content_type": mime,
                    })()
                except Exception:
                    pass

        # 没有 Web UI 可用
        return type("Response", (), {
            "status": 404,
            "body": '{"error": "Not Found"}',
            "headers": {"Content-Type": "application/json"},
            "content_type": "application/json",
        })()


def _guess_mime(filepath: str) -> str:
    """Guess MIME type from file extension"""
    ext = os.path.splitext(filepath)[1].lower()
    mime_map = {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".map": "application/json",
    }
    return mime_map.get(ext, "application/octet-stream")
