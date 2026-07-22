from typing import Any


class NamedError(Exception):
    """具名错误，带结构化数据"""

    def __init__(self, name: str, message: str = "", data: dict | None = None):
        self.error_name = name
        self.data = data or {}
        super().__init__(message or name)


class ErrorCode:
    """标准错误码"""
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_INPUT = "INVALID_INPUT"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INTERNAL = "INTERNAL"


def create_named_error(name: str, schema: type | None = None):
    """创建具名错误工厂"""

    def factory(message: str = "", **kwargs):
        return NamedError(name, message, kwargs)

    factory.__name__ = name
    return factory


def error_format(error: Any) -> str:
    """格式化错误为字符串（类似TS error.ts errorFormat）"""
    if isinstance(error, Exception):
        return f"{type(error).__name__}: {error}"
    if isinstance(error, dict):
        try:
            import json
            return json.dumps(error, indent=2, ensure_ascii=False)
        except Exception:
            return "Unexpected error (unserializable)"
    return str(error)


def error_message(error: Any) -> str:
    """提取错误消息（类似TS error.ts errorMessage）"""
    if isinstance(error, Exception):
        if str(error):
            return str(error)
        return type(error).__name__
    from .record import is_record
    if is_record(error) and isinstance(error.get("message"), str) and error["message"]:
        return error["message"]
    text = str(error)
    if text and text != "[object Object]":
        return text
    formatted = error_format(error)
    if formatted and formatted != "{}":
        return formatted
    return "unknown error"


def error_data(error: Any) -> dict:
    """提取错误结构化数据（类似TS error.ts errorData）"""
    if isinstance(error, Exception):
        return {
            "type": type(error).__name__,
            "message": error_message(error),
            "cause": str(error.__cause__) if error.__cause__ else None,
        }
    from .record import is_record
    if is_record(error):
        result = dict(error)
        if "message" not in result or not isinstance(result["message"], str):
            result["message"] = error_message(error)
        return result
    return {
        "type": type(error).__name__,
        "message": error_message(error),
    }
