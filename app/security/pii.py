"""
app/security/pii.py — PII masking for sample rows sent to the LLM.

Masks values in columns whose names match configured patterns,
and applies regex masking for email addresses and phone numbers.
Nothing masked here touches the actual database data.
"""
from __future__ import annotations

import re
from typing import Any

from app.config import get_settings

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{7,}\d)")


def _col_is_pii(col_name: str, pii_patterns: list[str]) -> bool:
    """Return True if the column name matches any PII pattern."""
    col_lower = col_name.lower()
    return any(pat in col_lower for pat in pii_patterns)


def _mask_value(value: Any) -> str:
    """Return a masked representation of a single value."""
    if value is None:
        return "null"
    s = str(value)
    if _EMAIL_RE.search(s):
        return "***@***.***"
    if _PHONE_RE.search(s):
        return "***-***-****"
    # Generic: keep first char, mask the rest
    if len(s) > 2:
        return s[0] + "*" * (min(len(s) - 1, 6))
    return "****"


def mask_sample_rows(
    rows: list[dict[str, Any]],
    column_names: list[str],
) -> list[dict[str, Any]]:
    """
    Mask PII columns in sample rows before they are sent to the LLM.
    Only called when pii_masking_enabled=True (checked by caller).

    Args:
        rows: List of row dicts (column_name -> value).
        column_names: All column names in the result set.

    Returns:
        New list of rows with PII values replaced by masked strings.
    """
    cfg = get_settings()
    if not cfg.pii_masking_enabled:
        return rows

    pii_patterns = cfg.pii_patterns_list
    pii_cols = {c for c in column_names if _col_is_pii(c, pii_patterns)}

    if not pii_cols:
        return rows

    masked = []
    for row in rows:
        new_row = {}
        for k, v in row.items():
            if k in pii_cols:
                new_row[k] = _mask_value(v)
            else:
                # Also scan values even in non-PII columns for email/phone
                if isinstance(v, str):
                    v = _EMAIL_RE.sub("***@***.***", v)
                    v = _PHONE_RE.sub("***-***-****", v)
                new_row[k] = v
        masked.append(new_row)
    return masked


def mask_export_rows(
    rows: list[dict[str, Any]],
    column_names: list[str],
) -> list[dict[str, Any]]:
    """Same masking but for export files when mask_pii_in_exports=True."""
    return mask_sample_rows(rows, column_names)
