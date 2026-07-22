"""
CLI Serve 命令 — 移植自 packages/opencode/src/cli/cmd/serve.ts
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def handle_serve(args: dict) -> None:
    """启动 HTTP 服务器"""
    host = args.get("host", "127.0.0.1")
    port = int(args.get("port", 7645))

    try:
        from craft.core.server import app, setup
        await setup()
        import uvicorn
        print(f"Serving on http://{host}:{port}")
        await uvicorn.run(app, host=host, port=port, log_level="info")
    except ImportError:
        print("Error: uvicorn not installed. Run: pip install uvicorn")
    except Exception as e:
        print(f"Failed to start server: {e}")
