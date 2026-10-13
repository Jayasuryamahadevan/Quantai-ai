"""
app/accuracy/number_checker.py — Verify that insight text only cites numbers from computed facts.

After the LLM writes an insight, this module:
1. Extracts every number in the text (integers, decimals, percentages)
2. Checks each against the computed facts (allowing rounding / formatting)
3. If any number is not found, triggers a regeneration or uses a template fallback
"""
from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)*(?:%)?")


def _normalize_number(s: str) -> float:
    """Convert a formatted number string to a float."""
    s = s.replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _extract_numbers(text: str) -> list[float]:
    """Extract all numbers from a text string."""
    raw = _NUMBER_RE.findall(text)
    nums = []
    for r in raw:
        n = _normalize_number(r)
        if not (n != n):  # not NaN
            nums.append(n)
    return nums


def _flatten_facts(facts: dict[str, Any]) -> list[float]:
    """Recursively extract all numeric values from a facts dict."""
    nums = []
    for v in facts.values():
        if isinstance(v, (int, float)):
            nums.append(float(v))
        elif isinstance(v, dict):
            nums.extend(_flatten_facts(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, (int, float)):
                    nums.append(float(item))
                elif isinstance(item, dict):
                    nums.extend(_flatten_facts(item))
    return nums


def _value_in_facts(value: float, fact_values: list[float], tolerance: float = 0.02) -> bool:
    """Check if a value appears in facts (within tolerance for rounding)."""
    for fv in fact_values:
        if fv == 0 and value == 0:
            return True
        if fv != 0 and abs(value - fv) / abs(fv) <= tolerance:
            return True
        # Also check if value is a percentage representation
        if fv != 0 and abs(value - fv * 100) / abs(fv * 100) <= tolerance:
            return True
        # Check if small number matches a rounded large number
        if abs(value - round(fv, 0)) < 1:
            return True
    return False


def check_insight_numbers(
    insight_text: str,
    computed_facts: dict[str, Any],
) -> dict[str, Any]:
    """
    Verify every number in the insight text appears in computed_facts.

    Args:
        insight_text: The LLM-generated insight string.
        computed_facts: Dict of computed statistics / metric values.

    Returns:
        {
          "valid": True/False,
          "invented_numbers": [list of numbers not found in facts],
          "checked_numbers": [all numbers found in insight],
          "fact_numbers": [all numbers from facts]
        }
    """
    insight_nums = _extract_numbers(insight_text)
    fact_nums = _flatten_facts(computed_facts)

    invented = []
    for num in insight_nums:
        # Skip small common numbers (1, 2, 3, etc.) that are likely ordinals
        if num in (1, 2, 3, 4, 5, 10, 100) or num == 0:
            continue
        if not _value_in_facts(num, fact_nums):
            invented.append(num)

    return {
        "valid": len(invented) == 0,
        "invented_numbers": invented,
        "checked_numbers": insight_nums,
        "fact_numbers": fact_nums[:20],  # Show sample for debugging
    }


def generate_template_insight(
    question: str,
    computed_facts: dict[str, Any],
    sql_result_preview: list[dict],
) -> str:
    """
    Generate a deterministic template-based insight when LLM insight fails number check.
    Uses only numbers from computed_facts.
    """
    parts = []

    # Extract top-level metrics
    if "headline_value" in computed_facts:
        val = computed_facts["headline_value"]
        col = computed_facts.get("headline_column", "metric")
        parts.append(f"The total {col} is {_format_number(val)}.")

    if "top_group" in computed_facts:
        tg = computed_facts["top_group"]
        parts.append(
            f"{tg.get('name', 'Top group')} had the highest value at "
            f"{_format_number(tg.get('value', 0))}."
        )

    if "row_count" in computed_facts:
        parts.append(f"The result contains {computed_facts['row_count']:,} rows.")

    if not parts and sql_result_preview:
        # Ultra-minimal: describe first row
        first = sql_result_preview[0]
        row_desc = ", ".join(f"{k}: {v}" for k, v in list(first.items())[:3])
        parts.append(f"Top result: {row_desc}.")

    if not parts:
        parts.append("The query completed successfully.")

    return " ".join(parts)


def _format_number(n: Any) -> str:
    """Format a number for display."""
    try:
        f = float(n)
        if f >= 1_000_000:
            return f"{f/1_000_000:.2f}M"
        elif f >= 1_000:
            return f"{f/1_000:.1f}K"
        elif f == int(f):
            return f"{int(f):,}"
        else:
            return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(n)
