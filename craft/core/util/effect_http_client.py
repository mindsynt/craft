"""HTTP 客户端辅助 — 移植自 effect-http-client.ts

为 HTTP 请求添加重试逻辑（指数退避 + 抖动）。
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable

import httpx

DEFAULT_RETRY_TIMES = 2
DEFAULT_BASE_DELAY_MS = 200


async def with_transient_retry(
    request_fn: Callable[[], Any],
    retry_times: int = DEFAULT_RETRY_TIMES,
    base_delay_ms: float = DEFAULT_BASE_DELAY_MS,
) -> Any:
    """执行 HTTP 请求并自动重试临时错误

    对应 TS withTransientReadRetry。使用指数退避 + 抖动。
    重试条件：连接错误、超时、5xx 状态码。
    """
    last_error: Exception | None = None

    for attempt in range(retry_times + 1):
        try:
            result = await request_fn()
            # httpx Response 有 status_code
            if hasattr(result, "status_code") and result.status_code >= 500:
                if attempt < retry_times:
                    delay = _jittered_delay(attempt, base_delay_ms)
                    await _sleep(delay / 1000.0)
                    continue
            return result
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            last_error = e
            if attempt < retry_times:
                delay = _jittered_delay(attempt, base_delay_ms)
                await _sleep(delay / 1000.0)
        except Exception as e:
            # 非重试性错误直接抛出
            raise

    raise last_error or RuntimeError("Request failed after retries")


def _jittered_delay(attempt: int, base_delay_ms: float) -> float:
    """指数退避 + 抖动"""
    delay = base_delay_ms * (2 ** attempt)
    jitter = random.uniform(0, delay * 0.5)
    return delay + jitter


async def _sleep(seconds: float):
    """异步睡眠"""
    import asyncio
    await asyncio.sleep(seconds)
