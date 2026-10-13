"""
app/agents/stats_analyzer.py — Statistical analysis agent (pure Pandas, no LLM).
Computes on query result columns only — never a 150x150 correlation matrix.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd

from app.graph.state import AgentState, cache_get, cache_put

log = logging.getLogger(__name__)


async def stats_analyzer_node(state: AgentState) -> dict[str, Any]:
    """Compute statistics on the query result."""
    t0 = time.perf_counter()
    step = "stats_analyzer"
    run_id = state["run_id"]

    try:
        df: pd.DataFrame | None = cache_get(run_id, "result_df")
        if df is None or df.empty:
            elapsed = int((time.perf_counter() - t0) * 1000)
            return {
                "stats": {},
                "computed_facts": {"row_count": 0},
                "current_step": step,
                "trace": state.get("trace", []) + [{"step": step, "status": "skipped_empty", "duration_ms": elapsed}],
            }

        stats = _compute_stats(df, state)

        # Extract computed facts for insight generation and number checking
        computed_facts = _extract_facts(df, stats, state)
        cache_put(run_id, "computed_facts", computed_facts)

        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "stats": stats,
            "computed_facts": computed_facts,
            "current_step": step,
            "trace": state.get("trace", []) + [{"step": step, "status": "completed", "duration_ms": elapsed}],
        }

    except Exception as exc:
        log.exception("Stats analyzer error")
        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "stats": {},
            "computed_facts": {},
            "current_step": step,
            "warnings": state.get("warnings", []) + [f"Stats computation warning: {exc}"],
            "trace": state.get("trace", []) + [{"step": step, "status": "warning", "duration_ms": elapsed}],
        }


def _compute_stats(df: pd.DataFrame, state: AgentState) -> dict[str, Any]:
    """Compute relevant statistics on the result DataFrame."""
    stats: dict[str, Any] = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
    }

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # Per-numeric-column summary
    col_stats = {}
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        col_stats[col] = {
            "sum": float(series.sum()),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "min": float(series.min()),
            "max": float(series.max()),
            "std": float(series.std()) if len(series) > 1 else 0.0,
            "null_count": int(df[col].isna().sum()),
        }
    stats["numeric"] = col_stats

    # Top-N rows (first numeric + first categorical)
    if numeric_cols:
        top_col = numeric_cols[-1]  # last numeric is usually the metric
        if len(df) > 1:
            top_n = df.nlargest(min(5, len(df)), top_col)
            stats["top_n"] = top_n.to_dict("records")
            stats["top_col"] = top_col

    # Growth rate (if result has 2+ rows with a consistent numeric metric)
    if len(df) >= 2 and numeric_cols:
        metric_col = numeric_cols[-1]
        values = df[metric_col].dropna().tolist()
        if len(values) >= 2 and values[0] != 0:
            stats["growth_rate_pct"] = round((values[-1] - values[0]) / abs(values[0]) * 100, 2)
            stats["trend_direction"] = "up" if values[-1] > values[0] else "down"

    # Correlations: only if question asks about it AND we have multiple numeric cols
    question = state.get("question", "").lower()
    if "correlat" in question or "drives" in question or "relationship" in question:
        if len(numeric_cols) >= 2:
            df_num = pd.DataFrame(df[numeric_cols])
            corr = df_num.corr()
            target = numeric_cols[-1]
            if target in corr.columns:
                target_series = pd.Series(corr[target])
                top_corr = (
                    target_series
                    .drop(labels=[target], errors="ignore")
                    .abs()
                    .sort_values(ascending=False)
                    .head(10)
                )
                stats["correlations"] = {
                    str(col): round(float(target_series.loc[col]), 3)
                    for col in top_corr.index
                }

    return stats


def _extract_facts(df: pd.DataFrame, stats: dict, state: AgentState) -> dict[str, Any]:
    """Extract key facts for insight generation and number checking."""
    facts: dict[str, Any] = {"row_count": len(df)}

    numeric = stats.get("numeric", {})
    if numeric:
        # Headline: first metric's sum and max
        first_col = list(numeric.keys())[0]
        facts["headline_column"] = first_col
        facts["headline_value"] = numeric[first_col].get("sum", numeric[first_col].get("max"))
        facts["headline_mean"] = numeric[first_col].get("mean")
        facts["headline_max"] = numeric[first_col].get("max")
        facts["headline_min"] = numeric[first_col].get("min")

    # Top group
    top_n = stats.get("top_n", [])
    if top_n:
        top_row = top_n[0]
        top_col = stats.get("top_col", "")
        cat_cols = [k for k, v in top_row.items() if isinstance(v, str)]
        if cat_cols:
            facts["top_group"] = {
                "name": str(top_row.get(cat_cols[0], "")),
                "value": float(top_row.get(top_col, 0)),
            }

    # Growth
    if "growth_rate_pct" in stats:
        facts["growth_rate_pct"] = stats["growth_rate_pct"]
        facts["trend_direction"] = stats.get("trend_direction")

    # Correlations
    if "correlations" in stats:
        facts["correlations"] = stats["correlations"]

    return facts
