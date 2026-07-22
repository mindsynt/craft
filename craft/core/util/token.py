import hashlib


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def estimate_tokens(text: str) -> int:
    """估算 token 数 — 移植自 token.ts estimate"""
    CHARS_PER_TOKEN = 4
    return max(0, round(len(text or "") / CHARS_PER_TOKEN))
