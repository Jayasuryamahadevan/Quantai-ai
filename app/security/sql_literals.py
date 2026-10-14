"""Validated SQL rendering helpers for the existing MySQL plan compiler.

Follow-up: migrate fully to SQLAlchemy bound parameters.
"""
from __future__ import annotations
import math
import re
from decimal import Decimal
from typing import Any

_IDENT = re.compile(r"[a-zA-Z_][a-zA-Z_0-9]*\Z")
_MONTH = re.compile(
    r"DATE_FORMAT\(\s*`?(?P<column>[a-zA-Z_][a-zA-Z_0-9]*)`?\s*,\s*'%Y-%m'\s*\)\Z",
    re.IGNORECASE,
)


def quote_identifier(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("SQL identifier must be a string")
    matched = _MONTH.fullmatch(name)
    if matched:
        return f"DATE_FORMAT(`{matched.group('column')}`, '%Y-%m')"
    unquoted = name[1:-1] if name.startswith('`') and name.endswith('`') else name
    if not _IDENT.fullmatch(unquoted):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f"`{unquoted}`"


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float, Decimal)):
        if not math.isfinite(float(value)):
            raise ValueError("Non-finite numeric SQL value")
        return str(value)
    if not isinstance(value, str):
        raise ValueError(f"Unsupported SQL value: {type(value).__name__}")
    return "'" + value.replace('\\', '\\\\').replace("'", "''") + "'"


def validated_direction(value: str) -> str:
    if not isinstance(value, str) or value.upper() not in {"ASC", "DESC"}:
        raise ValueError("ORDER BY direction must be ASC or DESC")
    return value.upper()


def validated_limit(value: Any, maximum: int = 1000) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("LIMIT must be a positive integer or null")
    return min(value, maximum)
