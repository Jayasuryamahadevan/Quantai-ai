"""
app/agents/cleaner.py — Data cleaning agent (vectorised Pandas only, no LLM).
Reports changes as summary counts, not per-cell logs.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd

from app.graph.state import AgentState, cache_get, cache_put

log = logging.getLogger(__name__)


async def cleaner_node(state: AgentState) -> dict[str, Any]:
    """
    Clean the query result DataFrame.
    Operates only on the result — not the full 150-column source.
    """
    t0 = time.perf_counter()
    step = "cleaner"
    run_id = state["run_id"]

    try:
        df: pd.DataFrame | None = cache_get(run_id, "result_df")
        if df is None or df.empty:
            elapsed = int((time.perf_counter() - t0) * 1000)
            return {
                "current_step": step,
                "trace": state.get("trace", []) + [{"step": step, "status": "skipped_empty", "duration_ms": elapsed}],
            }

        df_cleaned, changes = _clean_dataframe(df)
        cache_put(run_id, "result_df", df_cleaned)  # Replace with cleaned version

        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "current_step": step,
            "warnings": state.get("warnings", []) + [f"Cleaning: {c}" for c in changes],
            "trace": state.get("trace", []) + [{
                "step": step,
                "status": "completed",
                "duration_ms": elapsed,
                "changes": changes,
            }],
        }

    except Exception as exc:
        log.warning("Cleaner error: %s", exc)
        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "current_step": step,
            "trace": state.get("trace", []) + [{"step": step, "status": "warning", "duration_ms": elapsed}],
        }


def _clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Apply cleaning operations and return (cleaned_df, change_summary)."""
    changes = []
    df = df.copy()

    # 1. Strip whitespace from string columns
    str_cols = df.select_dtypes(include=["object"]).columns
    for col in str_cols:
        before = df[col].notna().sum()
        df[col] = df[col].str.strip() if hasattr(df[col], "str") else df[col]

    # 2. Try to parse date-like string columns
    for col in str_cols:
        sample = df[col].dropna().head(5).tolist()
        if _looks_like_date(sample):
            try:
                n_before = df[col].isna().sum()
                df[col] = pd.to_datetime(df[col], errors="coerce", infer_datetime_format=True)
                n_after = df[col].isna().sum()
                parsed = n_before - n_after + (len(df) - n_before)
                failed = n_after - n_before
                if parsed > 0:
                    changes.append(f"Parsed {parsed} dates in `{col}`")
                if failed > 0:
                    changes.append(f"⚠️ {failed} values could not be parsed as dates in `{col}`")
            except Exception:
                pass

    # 3. Downcast numeric columns
    for col in df.select_dtypes(include=[np.number]).columns:
        try:
            df[col] = pd.to_numeric(df[col], downcast="float")
        except Exception:
            pass

    # 4. Null percentage warning
    for col in df.columns:
        null_pct = df[col].isna().mean() * 100
        if null_pct > 50:
            changes.append(f"⚠️ Column `{col}` has {null_pct:.0f}% null values")

    return df, changes


def _looks_like_date(sample: list) -> bool:
    """Heuristic: does this column contain date-like strings?"""
    if not sample:
        return False
    date_indicators = ["-", "/", "T", "Z"]
    date_parts = ["20", "19", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    hits = 0
    for val in sample:
        s = str(val)
        if any(ind in s for ind in date_indicators) and any(p in s for p in date_parts):
            hits += 1
    return hits >= len(sample) // 2
