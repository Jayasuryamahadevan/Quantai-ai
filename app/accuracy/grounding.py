"""
app/accuracy/grounding.py — Value grounding and date/period resolution.

Value grounding: matches user-supplied filter values against real catalog values
Date resolution: resolves natural language like "last quarter", "this year" into exact dates
These run in deterministic Python — no LLM calls.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.config import get_settings

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATE RESOLUTION
# ─────────────────────────────────────────────────────────────────────────────

def _get_anchor(data_max_date: Optional[date] = None) -> date:
    """Return the anchor date based on config (data_max or today)."""
    cfg = get_settings()
    if cfg.date_anchor == "data_max" and data_max_date:
        return data_max_date
    return date.today()


def resolve_date_phrase(
    phrase: str,
    data_max_date: Optional[date] = None,
) -> tuple[Optional[date], Optional[date], str]:
    """
    Resolve a natural-language time phrase to (start, end, description).

    Returns:
        (start_date, end_date, human_readable_description)
        Returns (None, None, original_phrase) if phrase is not recognized.
    """
    phrase_lower = phrase.lower().strip()
    anchor = _get_anchor(data_max_date)
    today = anchor

    # Helper lambdas
    def quarter_bounds(d: date) -> tuple[date, date]:
        q = (d.month - 1) // 3
        q_start_month = q * 3 + 1
        q_end_month = q_start_month + 2
        start = date(d.year, q_start_month, 1)
        # Last day of end month
        if q_end_month == 12:
            end = date(d.year, 12, 31)
        else:
            end = date(d.year, q_end_month + 1, 1) - timedelta(days=1)
        return start, end

    def prev_quarter(d: date) -> tuple[date, date]:
        q = (d.month - 1) // 3  # 0-indexed current quarter
        if q == 0:
            # Previous quarter is Q4 of last year
            return date(d.year - 1, 10, 1), date(d.year - 1, 12, 31)
        else:
            pq_start_month = (q - 1) * 3 + 1
            pq_end_month = pq_start_month + 2
            start = date(d.year, pq_start_month, 1)
            end = date(d.year, pq_end_month + 1, 1) - timedelta(days=1)
            return start, end

    # Pattern matching
    if any(p in phrase_lower for p in ["last quarter", "previous quarter", "prior quarter"]):
        start, end = prev_quarter(today)
        return start, end, f"Last quarter ({start} to {end})"

    if any(p in phrase_lower for p in ["this quarter", "current quarter"]):
        start, end = quarter_bounds(today)
        return start, end, f"This quarter ({start} to {end})"

    if any(p in phrase_lower for p in ["this year", "current year", "ytd", "year to date"]):
        start = date(today.year, 1, 1)
        end = today
        return start, end, f"This year ({start} to {end})"

    if any(p in phrase_lower for p in ["last year", "previous year", "prior year"]):
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
        return start, end, f"Last year ({start} to {end})"

    if "last 30 days" in phrase_lower or "past 30 days" in phrase_lower:
        start = today - timedelta(days=30)
        return start, today, f"Last 30 days ({start} to {today})"

    if "last 90 days" in phrase_lower or "past 90 days" in phrase_lower:
        start = today - timedelta(days=90)
        return start, today, f"Last 90 days ({start} to {today})"

    if "last 6 months" in phrase_lower or "past 6 months" in phrase_lower:
        start = today - timedelta(days=183)
        return start, today, f"Last 6 months ({start} to {today})"

    if "last 12 months" in phrase_lower or "past 12 months" in phrase_lower or "last year" in phrase_lower:
        start = today - timedelta(days=365)
        return start, today, f"Last 12 months ({start} to {today})"

    # "last N days/weeks/months"
    m = re.search(r"last\s+(\d+)\s+(day|week|month)s?", phrase_lower)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "day":
            start = today - timedelta(days=n)
        elif unit == "week":
            start = today - timedelta(weeks=n)
        else:  # month
            start = today - timedelta(days=n * 30)
        return start, today, f"Last {n} {unit}s ({start} to {today})"

    # Specific year: "in 2025", "for 2025", "2025"
    m = re.search(r"\b(20\d\d)\b", phrase_lower)
    if m:
        yr = int(m.group(1))
        start = date(yr, 1, 1)
        end = date(yr, 12, 31)
        return start, end, f"Year {yr} ({start} to {end})"

    return None, None, phrase


def resolve_time_range_from_plan(
    time_range: Optional[dict[str, Any]],
    data_max_date: Optional[date] = None,
) -> Optional[dict[str, str]]:
    """
    If time_range in plan has unresolved phrases, resolve them.
    Returns updated time_range dict or None.
    """
    if not time_range:
        return None

    start_str = time_range.get("start", "")
    end_str = time_range.get("end", "")

    # If already in YYYY-MM-DD format, return as-is
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if date_re.match(start_str) and date_re.match(end_str):
        return time_range

    # Try resolving combined phrase
    for phrase in [start_str, end_str, f"{start_str} {end_str}"]:
        start, end, desc = resolve_date_phrase(phrase, data_max_date)
        if start and end:
            return {
                "column": time_range.get("column", ""),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "description": desc,
            }

    return time_range


# ─────────────────────────────────────────────────────────────────────────────
# VALUE GROUNDING
# ─────────────────────────────────────────────────────────────────────────────

def ground_filter_value(
    value: str,
    catalog_col: dict[str, Any],
    threshold: float = 70.0,
) -> dict[str, Any]:
    """
    Match a filter value to a real value in the column's catalog.

    Args:
        value: The value from the query plan (may be user-typed like "north").
        catalog_col: The column catalog entry with top_values list.
        threshold: Minimum fuzzy match score (0-100) to accept a match.

    Returns:
        {
          "original": value,
          "matched": matched_value_or_None,
          "score": 0-100,
          "alternatives": [list of top alternatives],
          "grounded": True/False
        }
    """
    top_values = catalog_col.get("top_values") or []
    if not top_values:
        # No catalog values available — can't ground, proceed as-is
        return {
            "original": value,
            "matched": value,
            "score": 100,
            "alternatives": [],
            "grounded": False,  # unknown
        }

    try:
        from rapidfuzz import fuzz, process

        # Check for exact match (case-insensitive)
        value_lower = str(value).lower()
        for tv in top_values:
            if str(tv).lower() == value_lower:
                return {
                    "original": value,
                    "matched": tv,
                    "score": 100,
                    "alternatives": [],
                    "grounded": True,
                }

        # Also check dictionary synonyms
        synonyms = catalog_col.get("synonyms") or {}
        if isinstance(synonyms, dict):
            for syn_key, real_val in synonyms.items():
                if value_lower == syn_key.lower():
                    return {
                        "original": value,
                        "matched": real_val,
                        "score": 100,
                        "alternatives": [],
                        "grounded": True,
                    }

        # Fuzzy match
        str_values = [str(v) for v in top_values]
        result = process.extractOne(
            str(value),
            str_values,
            scorer=fuzz.ratio,
        )

        if result and result[1] >= threshold:
            matched = top_values[str_values.index(result[0])]
            alternatives = [
                r[0] for r in process.extract(str(value), str_values, limit=5)
                if r[0] != result[0]
            ]
            return {
                "original": value,
                "matched": matched,
                "score": result[1],
                "alternatives": alternatives,
                "grounded": True,
            }
        else:
            # No good match
            alternatives = [r[0] for r in (process.extract(str(value), str_values, limit=5) or [])]
            return {
                "original": value,
                "matched": None,
                "score": result[1] if result else 0,
                "alternatives": alternatives,
                "grounded": False,
            }

    except ImportError:
        log.warning("rapidfuzz not installed, skipping value grounding")
        return {
            "original": value,
            "matched": value,
            "score": 0,
            "alternatives": [],
            "grounded": False,
        }


def ground_plan_filters(
    plan: dict[str, Any],
    catalog: dict[str, dict[str, Any]],  # safe_name -> catalog entry
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Ground all filter values in a plan against the catalog.

    Returns:
        (updated_plan, grounding_issues) where grounding_issues is a list
        of issues to show the user (unmatched values, substitutions).
    """
    issues = []
    updated_filters = []

    for flt in plan.get("filters", []):
        col_name = flt.get("column", "")
        value = flt.get("value")
        col_catalog = catalog.get(col_name, {})

        if value is None or col_catalog.get("col_type") not in ("str", "category"):
            updated_filters.append(flt)
            continue

        result = ground_filter_value(str(value), col_catalog)

        if not result["grounded"] and result["matched"] is None:
            issues.append({
                "type": "no_match",
                "column": col_name,
                "value": value,
                "alternatives": result["alternatives"],
                "message": (
                    f"Value '{value}' not found in column '{col_name}'. "
                    f"Closest matches: {result['alternatives'][:3]}"
                ),
            })
            updated_filters.append(flt)  # keep original, query may return empty
        elif result["matched"] != value:
            issues.append({
                "type": "substituted",
                "column": col_name,
                "original": value,
                "matched": result["matched"],
                "score": result["score"],
                "message": (
                    f"Matched '{value}' → '{result['matched']}' "
                    f"in column '{col_name}' (score: {result['score']:.0f})"
                ),
            })
            updated_filters.append({**flt, "value": result["matched"]})
        else:
            updated_filters.append(flt)

    updated_plan = {**plan, "filters": updated_filters}
    return updated_plan, issues
