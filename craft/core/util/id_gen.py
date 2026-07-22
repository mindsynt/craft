import uuid


def generate_id(prefix: str = "") -> str:
    """生成唯一 ID"""
    return f"{prefix}{uuid.uuid4().hex[:16]}"
