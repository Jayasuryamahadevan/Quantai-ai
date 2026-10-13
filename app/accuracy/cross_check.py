"""
app/accuracy/cross_check.py — Independent Pandas cross-verification of SQL results.

After running a SQL query, we recompute the headline result using Pandas
on the same data to verify correctness. A "Verified" badge is shown on match.
On mismatch, we do not present the SQL result as final.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

import pandas as pd
import numpy as np

log = logging.getLogger(__name__)

TOLERANCE = 0.01  # 1% relative tolerance for numeric comparison


def _rel_diff(a: float, b: float) -> float:
    """Relative difference between two numbers."""
    if b == 0:
        return 0.0 if a == 0 else float("inf")
    return abs(a - b) / abs(b)


def cross_check_result(
    plan: dict[str, Any],
    sql_result: pd.DataFrame,
    full_df: pd.DataFrame,
    tolerance: float = TOLERANCE,
) -> dict[str, Any]:
    """
    Recompute the headline metric(s) from the plan using Pandas on full_df,
    then compare with the SQL result.

    Args:
        plan: The validated query plan dict.
        sql_result: DataFrame returned by SQL execution.
        full_df: Full dataset as a Pandas DataFrame (loaded in memory).
        tolerance: Relative tolerance for numeric comparison.

    Returns:
        {
          "verified": True/False,
          "pandas_value": computed_value,
          "sql_value": sql_value,
          "relative_diff": float,
          "details": str,
          "error": str or None
        }
    """
    try:
        metrics = plan.get("metrics", [])
        group_by = plan.get("group_by", [])
        time_range = plan.get("time_range")
        filters = plan.get("filters", [])

        if not metrics or sql_result.empty:
            return {
                "verified": None,
                "pandas_value": None,
                "sql_value": None,
                "relative_diff": None,
                "details": "No metrics to verify or empty result",
                "error": None,
            }

        # Apply time filter on full_df
        working_df: Any = full_df.copy()
        if time_range:
            col = time_range.get("column")
            start = time_range.get("start")
            end = time_range.get("end")
            if col and col in working_df.columns:
                try:
                    working_df[col] = pd.to_datetime(working_df[col])
                    if start:
                        working_df = working_df[working_df[col] >= pd.Timestamp(start)]
                    if end:
                        working_df = working_df[working_df[col] <= pd.Timestamp(end)]
                except Exception:
                    pass

        # Apply other filters
        for flt in filters:
            col = flt.get("column")
            op = str(flt.get("op", "=")).lower()
            value = flt.get("value")
            if col not in working_df.columns:
                continue
            try:
                if op in ("=", "=="):
                    working_df = working_df[working_df[col].astype(str).str.lower() == str(value).lower()]
                elif op == "!=":
                    working_df = working_df[working_df[col].astype(str).str.lower() != str(value).lower()]
                elif op == ">":
                    working_df = working_df[working_df[col] > float(value)]
                elif op == "<":
                    working_df = working_df[working_df[col] < float(value)]
                elif op == ">=":
                    working_df = working_df[working_df[col] >= float(value)]
                elif op == "<=":
                    working_df = working_df[working_df[col] <= float(value)]
                elif op == "in":
                    vals = value if isinstance(value, list) else [value]
                    working_df = working_df[working_df[col].isin(vals)]
            except Exception:
                pass  # Skip filter if types don't match

        # Compute first metric
        m = metrics[0]
        col = m["column"]
        agg = m.get("agg", "sum").lower()

        if col not in working_df.columns:
            return {
                "verified": None,
                "pandas_value": None,
                "sql_value": None,
                "relative_diff": None,
                "details": f"Column '{col}' not found in loaded data",
                "error": None,
            }

        # Grouped aggregation
        if group_by:
            valid_groups = [g for g in group_by if g in working_df.columns and "DATE_FORMAT" not in g]
            if not valid_groups:
                return {
                    "verified": None,
                    "pandas_value": None,
                    "sql_value": None,
                    "relative_diff": None,
                    "details": "Group-by columns contain expressions — skipping cross-check",
                    "error": None,
                }
            if agg == "sum":
                pandas_grouped = working_df.groupby(valid_groups)[col].sum()
            elif agg == "avg":
                pandas_grouped = working_df.groupby(valid_groups)[col].mean()
            elif agg in ("count", "count_distinct"):
                pandas_grouped = working_df.groupby(valid_groups)[col].nunique()
            else:
                pandas_grouped = working_df.groupby(valid_groups)[col].sum()

            pandas_top = float(pandas_grouped.max())
            # Get corresponding value from SQL result
            sql_top = _extract_first_metric_value(sql_result, agg, col)

        else:
            # Global aggregation
            if agg == "sum":
                pandas_val = float(working_df[col].sum())
            elif agg == "avg":
                pandas_val = float(working_df[col].mean())
            elif agg == "count":
                pandas_val = float(len(working_df))
            elif agg == "count_distinct":
                pandas_val = float(working_df[col].nunique())
            elif agg == "min":
                pandas_val = float(working_df[col].min())
            elif agg == "max":
                pandas_val = float(working_df[col].max())
            elif agg == "median":
                pandas_val = float(working_df[col].median())
            else:
                pandas_val = float(working_df[col].sum())

            pandas_top = pandas_val
            sql_top = _extract_first_metric_value(sql_result, agg, col)

        if sql_top is None:
            return {
                "verified": None,
                "pandas_value": pandas_top,
                "sql_value": None,
                "relative_diff": None,
                "details": "Could not extract metric value from SQL result",
                "error": None,
            }

        rel_diff = _rel_diff(float(sql_top), float(pandas_top))
        verified = rel_diff <= tolerance

        return {
            "verified": verified,
            "pandas_value": pandas_top,
            "sql_value": float(sql_top),
            "relative_diff": rel_diff,
            "details": (
                f"Pandas: {pandas_top:.2f}, SQL: {sql_top:.2f}, "
                f"diff: {rel_diff*100:.2f}%"
            ),
            "error": None,
        }

    except Exception as exc:
        log.warning("Cross-check failed: %s", exc, exc_info=True)
        return {
            "verified": None,
            "pandas_value": None,
            "sql_value": None,
            "relative_diff": None,
            "details": f"Cross-check error: {exc}",
            "error": str(exc),
        }


def _extract_first_metric_value(
    df: pd.DataFrame,
    agg: str,
    col: str,
) -> Optional[float]:
    """Extract the first numeric metric value from a SQL result DataFrame."""
    # Try to find a column matching the expected alias pattern
    alias_candidates = [
        f"{agg}_{col}",
        f"count_distinct_{col}",
        f"median_{col}",
        col,
    ]
    for alias in alias_candidates:
        if alias in df.columns:
            try:
                return float(df[alias].iloc[0])
            except (ValueError, TypeError, IndexError):
                continue

    # Try any numeric column
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if numeric_cols:
        try:
            return float(df[numeric_cols[-1]].iloc[0])
        except (ValueError, TypeError, IndexError):
            return None
    return None
