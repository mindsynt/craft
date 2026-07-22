import os


async def fetch_json(url: str, timeout: float = 10) -> dict | None:
    """HTTP GET 请求"""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def is_online() -> bool:
    """检查网络是否在线 — 移植自 network.ts online"""
    return True


def is_proxied() -> bool:
    """检查是否使用代理 — 移植自 network.ts proxied"""
    return bool(os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
                or os.environ.get("http_proxy") or os.environ.get("https_proxy"))
