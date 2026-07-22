"""Web fetch tool."""

import re
from urllib.parse import urlparse

import httpx

from .registry import tool


@tool(name="webfetch", description="从 URL 获取内容(HTTP 请求)",
      parameters={
          "type": "object",
          "properties": {
              "url": {"type": "string", "description": "要获取的 URL"},
              "format": {"type": "string", "enum": ["text", "markdown", "html"],
                         "description": "返回格式(默认 markdown)"},
              "timeout": {"type": "integer", "description": "超时时间(秒, 最大 120)"},
          },
          "required": ["url"],
      })
async def webfetch(url: str, format: str = "markdown", timeout: int = 30) -> str:
    try:
        if not url.startswith(("http://", "https://")):
            return "[错误] URL 必须以 http:// 或 https:// 开头"

        parsed = urlparse(url)
        if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            return "[错误] 不允许获取本地地址"

        timeout = min(timeout, 120)

        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/143.0.0.0 Safari/537.36"),
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            content = resp.text

            if "text/html" in content_type and format == "markdown":
                # Simple HTML to text conversion
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()
                content = content[:50000]

            return f"URL: {url}\nContent-Type: {content_type}\n\n{content[:30000]}"
    except httpx.TimeoutException:
        return "[超时] 请求超时"
    except httpx.HTTPStatusError as e:
        return f"[HTTP {e.response.status_code}] {e.response.reason_phrase}"
    except Exception as e:
        return f"[错误] {e}"
