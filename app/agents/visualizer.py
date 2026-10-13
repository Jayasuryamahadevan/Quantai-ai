"""
app/agents/visualizer.py — Visualization agent (deterministic chart type selection).
Generates Plotly figure JSON based on result shape — no LLM involved.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.graph.state import AgentState, cache_get

log = logging.getLogger(__name__)


def _select_chart_type(df: pd.DataFrame, stats: dict) -> str:
    """
    Deterministically select the best chart type from result shape.

    Rules:
      - 1 categorical + 1 numeric + time-like col name → line
      - 1 categorical + 1 numeric, <=8 categories → bar
      - 1 categorical + 1 numeric, share question → pie (max 8 cats)
      - 2 numeric cols → scatter
      - 1 col → histogram
      - Multiple numeric cols over categories → grouped_bar
      - Default → bar
    """
    cols = list(df.columns)
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    text_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols = [c for c in cols if any(
        kw in c.lower() for kw in ["date", "month", "year", "quarter", "week", "period", "time"]
    )]

    n_num = len(numeric)
    n_cat = len(text_cols)
    n_rows = len(df)

    if n_num == 0:
        return "table"

    if n_num == 1 and (date_cols or (n_cat == 1 and n_rows >= 6)):
        return "line"

    if n_num == 1 and n_cat == 1:
        n_unique = df[text_cols[0]].nunique()
        if n_unique <= 8:
            return "bar"
        return "bar"

    if n_num >= 2 and n_cat == 0:
        return "scatter"

    if n_num >= 2 and n_cat >= 1:
        return "grouped_bar"

    if n_num == 1 and n_cat == 0:
        return "histogram"

    return "bar"


async def visualizer_node(state: AgentState) -> dict[str, Any]:
    """Generate a Plotly chart from the query result."""
    t0 = time.perf_counter()
    step = "visualizer"
    run_id = state["run_id"]

    try:
        df: pd.DataFrame | None = cache_get(run_id, "result_df")
        if df is None or df.empty:
            elapsed = int((time.perf_counter() - t0) * 1000)
            return {
                "chart_json": None,
                "chart_type": None,
                "current_step": step,
                "trace": state.get("trace", []) + [{"step": step, "status": "skipped_empty", "duration_ms": elapsed}],
            }

        stats = state.get("stats") or {}
        question = state.get("question", "").lower()

        chart_type = _select_chart_type(df, stats)

        # Override for pie if question mentions "share" / "proportion" / "breakdown"
        share_keywords = ["share", "proportion", "breakdown", "distribution", "percent", "pie"]
        if any(kw in question for kw in share_keywords):
            cols = list(df.columns)
            numeric = df.select_dtypes(include=[np.number]).columns.tolist()
            text_cols = df.select_dtypes(include=["object"]).columns.tolist()
            if text_cols and numeric and df[text_cols[0]].nunique() <= 8:
                chart_type = "pie"

        fig = _build_chart(df, chart_type, state)

        # Apply consistent styling
        fig = _apply_theme(fig)

        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "chart_json": fig.to_dict(),
            "chart_type": chart_type,
            "current_step": step,
            "trace": state.get("trace", []) + [{
                "step": step,
                "status": "completed",
                "duration_ms": elapsed,
                "chart_type": chart_type,
            }],
        }

    except Exception as exc:
        log.exception("Visualizer error")
        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "chart_json": None,
            "chart_type": None,
            "current_step": step,
            "warnings": state.get("warnings", []) + [f"Chart generation failed: {exc}"],
            "trace": state.get("trace", []) + [{"step": step, "status": "warning", "duration_ms": elapsed}],
        }


def _build_chart(df: pd.DataFrame, chart_type: str, state: AgentState) -> go.Figure:
    """Build a Plotly figure for the given chart type."""
    question = state.get("question", "")
    table_name = state.get("table_name", "Result")

    cols = list(df.columns)
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    text_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # Preview limited rows for chart (chart itself handles display)
    chart_df = df.head(100)  # chart shows top 100 for readability

    if chart_type == "bar":
        x_col = text_cols[0] if text_cols else cols[0]
        y_col = numeric[-1] if numeric else cols[-1]
        fig = px.bar(chart_df, x=x_col, y=y_col, title=question[:80])

    elif chart_type == "line":
        # Sort by x-axis for time series
        date_cols = [c for c in cols if any(
            kw in c.lower() for kw in ["date", "month", "year", "quarter", "week", "period", "time"]
        )]
        x_col = date_cols[0] if date_cols else (text_cols[0] if text_cols else cols[0])
        y_col = numeric[-1] if numeric else cols[-1]
        sorted_df = chart_df.sort_values(x_col)
        fig = px.line(sorted_df, x=x_col, y=y_col, title=question[:80], markers=True)

    elif chart_type == "pie":
        name_col = text_cols[0] if text_cols else cols[0]
        val_col = numeric[-1] if numeric else cols[-1]
        fig = px.pie(chart_df, names=name_col, values=val_col, title=question[:80])

    elif chart_type == "scatter":
        x_col = numeric[0] if len(numeric) >= 2 else cols[0]
        y_col = numeric[1] if len(numeric) >= 2 else cols[1]
        color_col = text_cols[0] if text_cols else None
        fig = px.scatter(chart_df, x=x_col, y=y_col, color=color_col, title=question[:80])

    elif chart_type == "histogram":
        col = numeric[0] if numeric else cols[0]
        fig = px.histogram(chart_df, x=col, title=question[:80])

    elif chart_type == "grouped_bar":
        x_col = text_cols[0] if text_cols else cols[0]
        fig = go.Figure()
        for num_col in numeric[:5]:  # max 5 series
            fig.add_trace(go.Bar(name=num_col, x=chart_df[x_col], y=chart_df[num_col]))
        fig.update_layout(barmode="group", title=question[:80])

    else:
        # Fallback: simple bar
        x_col = cols[0]
        y_col = numeric[0] if numeric else cols[min(1, len(cols) - 1)]
        fig = px.bar(chart_df, x=x_col, y=y_col, title=question[:80])

    return fig


def _apply_theme(fig: go.Figure) -> go.Figure:
    """Apply consistent QuantAI theme to the chart."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, system-ui, sans-serif", "size": 13},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        legend={"orientation": "h", "y": -0.15},
        colorway=["#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444"],
        xaxis={"showgrid": False, "zeroline": False},
        yaxis={"showgrid": True, "gridcolor": "rgba(100,100,100,0.15)", "zeroline": False},
        hovermode="x unified",
    )
    return fig
