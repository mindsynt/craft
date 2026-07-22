"""ID schema types — ported from schema.ts."""

import re
import secrets
import string


def _make_id(prefix: str, suffix: str | None = None) -> str:
    """Generate a typed ID like 'ses_a1b2c3d4e5f6' or 'msg_...'."""
    raw = suffix or secrets.token_hex(8)
    return f"{prefix}_{raw}"


def _descending_id(prefix: str, seed: str | None = None) -> str:
    """Generate a descending-sortable ID (reverse-chronological)."""
    raw = seed or secrets.token_hex(8)
    return _make_id(prefix, raw)


def _ascending_id(prefix: str, seed: str | None = None) -> str:
    """Generate an ascending-sortable ID (chronological)."""
    raw = seed or secrets.token_hex(8)
    return _make_id(prefix, raw)


class SessionID(str):
    """Typed session ID — 'ses_' prefix."""

    @classmethod
    def make(cls, id: str | None = None) -> "SessionID":
        return cls(id) if id and id.startswith("ses_") else cls(_make_id("ses", id))

    @classmethod
    def descending(cls, id: str | None = None) -> "SessionID":
        return cls(_descending_id("ses", id))

    @classmethod
    def zod(cls) -> type:
        return cls  # placeholder for schema validation


class MessageID(str):
    """Typed message ID — 'msg_' prefix."""

    @classmethod
    def make(cls, id: str | None = None) -> "MessageID":
        return cls(id) if id and id.startswith("msg_") else cls(_make_id("msg", id))

    @classmethod
    def ascending(cls, id: str | None = None) -> "MessageID":
        return cls(_ascending_id("msg", id))

    @classmethod
    def zod(cls) -> type:
        return cls


class PartID(str):
    """Typed part ID — 'part_' prefix."""

    @classmethod
    def make(cls, id: str | None = None) -> "PartID":
        return cls(id) if id and id.startswith("part_") else cls(_make_id("part", id))

    @classmethod
    def ascending(cls, id: str | None = None) -> "PartID":
        return cls(_ascending_id("part", id))

    @classmethod
    def zod(cls) -> type:
        return cls
