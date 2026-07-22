"""提供商优先级 — 移植自 provider-priority.ts

提供商排序和优先级定义，用于 UI 展示顺序。
"""

from __future__ import annotations

# 头部热门提供商
HEAD_POPULAR_PROVIDERS = ["xiaomi", "openai", "anthropic"]

# 中国热门提供商（阿里之前）
CHINA_POPULAR_BEFORE_ALIBABA = [
    "deepseek",
    "zai",
    "zhipuai",
    "moonshotai",
    "moonshotai-cn",
    "kimi-for-coding",
    "stepfun",
]

# 中间热门提供商
MID_POPULAR_PROVIDERS = ["opencode", "openrouter"]

# 中国热门提供商（阿里及之后）
CHINA_POPULAR_FROM_ALIBABA = [
    "alibaba",
    "alibaba-cn",
    "bytedance",
    "alibaba-coding-plan",
    "alibaba-coding-plan-cn",
    "zai-coding-plan",
    "zhipuai-coding-plan",
    "tencent-coding-plan",
    "minimax-coding-plan",
    "minimax-cn-coding-plan",
    "kuae-cloud-coding-plan",
]

# 尾部热门提供商
TAIL_POPULAR_PROVIDERS = ["opencode-go", "github-copilot", "google", "vercel"]

POPULAR_PROVIDER_GROUPS = [
    HEAD_POPULAR_PROVIDERS,
    CHINA_POPULAR_BEFORE_ALIBABA,
    MID_POPULAR_PROVIDERS,
    CHINA_POPULAR_FROM_ALIBABA,
    TAIL_POPULAR_PROVIDERS,
]


def _build_priority() -> dict[str, int]:
    """构建提供商优先级映射"""
    priority: dict[str, int] = {}
    index = 0
    for group in POPULAR_PROVIDER_GROUPS:
        for provider_id in group:
            priority[provider_id] = index
            index += 1
    return priority


PROVIDER_PRIORITY: dict[str, int] = _build_priority()


def is_popular_provider(provider_id: str) -> bool:
    """判断是否为热门提供商

    对应 TS isPopularProvider()。
    """
    return provider_id in PROVIDER_PRIORITY
