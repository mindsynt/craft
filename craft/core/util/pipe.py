from typing import Any, Callable


def pipe(value: Any, *fns: Callable) -> Any:
    """管道操作"""
    for fn in fns:
        value = fn(value)
    return value
