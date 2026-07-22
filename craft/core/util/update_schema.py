"""更新 Schema — 移植自 update-schema.ts

将 Zod Object Schema 的所有字段变为 nullable optional，用于部分更新。
"""

from __future__ import annotations

from typing import Any


def make_update_schema(fields: dict[str, Any]) -> dict[str, Any]:
    """创建所有字段为 nullable optional 的更新 schema

    对应 TS updateSchema()。将 schema 中的每个字段变为 nullable 和 optional，
    用于 PATCH / 部分更新场景。

    参数:
        fields: 字段名到类型的映射（如 zod schema 的 shape）

    返回:
        所有字段为 nullable optional 的新 schema 字典
    """
    result: dict[str, Any] = {}
    for name, field_type in fields.items():
        result[name] = _make_nullable_optional(field_type)
    return result


def _make_nullable_optional(field_type: Any) -> Any:
    """将字段类型标记为 nullable 和 optional

    在 Python 中，这通常意味着 Optional[type] = None。
    返回包含类型信息和标记的字典。
    """
    return {
        "type": field_type,
        "nullable": True,
        "optional": True,
    }
