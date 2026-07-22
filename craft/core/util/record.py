from typing import Any


def is_record(value: Any) -> bool:
    """检查值是否为字典（类似TS的isRecord）"""
    return isinstance(value, dict)
