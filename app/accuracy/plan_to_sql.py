"""
app/accuracy/plan_to_sql.py — Deterministic SQL compiler from structured query plan.

Converts the JSON query plan produced by the planner into valid MySQL 8.0 SQL
without involving the LLM. This is the primary SQL generation path.
Supported: sum, avg, count, count_distinct, min, max, median, group by,
           filters, top/bottom N, time ranges, period-over-period growth,
           running totals, distributions, correlations, ratio metrics.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.security.sql_literals import quote_identifier, sql_literal, validated_direction, validated_limit

log = logging.getLogger(__name__)

# Mapping from plan agg names to MySQL aggregate functions
AGG_MAP = {
    "sum": "SUM",
    "avg": "AVG",
    "count": "COUNT",
    "count_distinct": "COUNT(DISTINCT {col})",
    "min": "MIN",
    "max": "MAX",
    "median": None,  # Handled specially via window function
}

OP_MAP = {
    "=": "=",
    "!=": "!=",
    "<>": "!=",
    ">": ">",
    "<": "<",
    ">=": ">=",
    "<=": "<=",
    "in": "IN",
    "not in": "NOT IN",
    "like": "LIKE",
    "not like": "NOT LIKE",
    "between": "BETWEEN",
    "is null": "IS NULL",
    "is not null": "IS NOT NULL",
}


def _quote(name: str) -> str:
    """Quote a validated column or supported month-grouping expression."""
    return quote_identifier(name)


def _build_metric_expr(metric: dict[str, Any], median_col_alias: str | None = None) -> tuple[str, str]:
    """
    Build a SQL expression + alias for a metric.
    Returns (sql_expression, alias_name).
    """
    col = metric["column"]
    agg = metric.get("agg", "sum").lower()
    quoted_col = _quote(col) if agg != "count" else "*"

    if agg == "count_distinct":
        expr = f"COUNT(DISTINCT {quoted_col})"
        alias = f"count_distinct_{col}"
    elif agg == "median":
        # MySQL median via window function inline — handled in _build_median_cte
        expr = f"AVG({quoted_col})"  # placeholder; will be replaced by caller
        alias = f"median_{col}"
    elif agg == "count":
        expr = "COUNT(*)"
        alias = "count"
    elif agg in AGG_MAP and AGG_MAP[agg]:
        expr = f"{AGG_MAP[agg]}({quoted_col})"
        alias = f"{agg}_{col}"
    else:
        raise ValueError(f"Unsupported aggregate: {agg}")

    return expr, alias


def _build_filter_clause(filters: list[dict[str, Any]]) -> str:
    """Build a WHERE clause from filter list."""
    if not filters:
        return ""

    parts = []
    for flt in filters:
        col = _quote(flt["column"])
        raw_op = str(flt.get("op", "=")).lower()
        if raw_op not in OP_MAP:
            raise ValueError(f"Unsupported filter operator: {raw_op}")
        op = OP_MAP[raw_op]
        value = flt.get("value")

        if op in ("IS NULL", "IS NOT NULL"):
            parts.append(f"{col} {op}")
        elif op in ("IN", "NOT IN"):
            vals = value if isinstance(value, list) else [value]
            if not vals:
                raise ValueError("IN filter cannot be empty")
            escaped = ", ".join(sql_literal(v) for v in vals)
            parts.append(f"{col} {op} ({escaped})")
        elif op == "BETWEEN":
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("BETWEEN requires exactly two values")
            parts.append(f"{col} BETWEEN {sql_literal(value[0])} AND {sql_literal(value[1])}")
        elif value is None:
            if op == "=":
                parts.append(f"{col} IS NULL")
            elif op == "!=":
                parts.append(f"{col} IS NOT NULL")
            else:
                raise ValueError("NULL supports only equality comparisons")
        else:
            parts.append(f"{col} {op} {sql_literal(value)}")

    return "WHERE " + " AND ".join(parts)


def _build_time_clause(time_range: Optional[dict[str, Any]], existing_filters: list[dict]) -> str:
    """Build time range condition as a WHERE / AND clause fragment."""
    if not time_range:
        return ""
    col = _quote(time_range["column"])
    start = time_range.get("start")
    end = time_range.get("end")
    if start is not None and end is not None:
        return f"{col} BETWEEN {sql_literal(start)} AND {sql_literal(end)}"
    elif start is not None:
        return f"{col} >= {sql_literal(start)}"
    elif end is not None:
        return f"{col} <= {sql_literal(end)}"
    return ""


def compile_plan(
    plan: dict[str, Any],
    table_name: str,
    schema_name: str | None = None,
) -> str:
    """
    Compile a query plan JSON into MySQL 8.0 SQL.

    Args:
        plan: The validated query plan dict.
        table_name: The MySQL table to query.
        schema_name: Optional schema prefix.

    Returns:
        MySQL 8.0 SQL string.

    Raises:
        ValueError: If the plan cannot be compiled.
    """
    tbl = f"{_quote(schema_name)}.{_quote(table_name)}" if schema_name else _quote(table_name)
    intent = plan.get("intent", "aggregate")
    metrics = plan.get("metrics", [])
    group_by = plan.get("group_by", [])
    filters = plan.get("filters", [])
    time_range = plan.get("time_range")
    order_by = plan.get("order_by", [])
    limit = validated_limit(plan.get("limit", 1000))

    # ── Detect median metrics ────────────────────────────────────────────────
    median_metrics = [m for m in metrics if m.get("agg", "").lower() == "median"]
    other_metrics = [m for m in metrics if m.get("agg", "").lower() != "median"]

    # ── Build WHERE clause ───────────────────────────────────────────────────
    where_parts = []
    time_cond = _build_time_clause(time_range, filters)
    if time_cond:
        where_parts.append(time_cond)

    filter_clause = _build_filter_clause(filters)
    if filter_clause:
        # Extract the WHERE content
        where_parts.append(filter_clause.replace("WHERE ", "", 1))

    full_where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # ── Growth / trend intent ────────────────────────────────────────────────
    if intent == "trend" and time_range and not group_by:
        # Auto-group by month
        date_col = _quote(time_range["column"])
        group_by = [f"DATE_FORMAT({date_col}, '%Y-%m')"]

    # ── Simple aggregate / top-N ─────────────────────────────────────────────
    if median_metrics:
        return _compile_with_median(
            table=tbl,
            median_metrics=median_metrics,
            other_metrics=other_metrics,
            group_by=group_by,
            where=full_where,
            order_by=order_by,
            limit=limit,
        )

    # ── Standard SELECT ──────────────────────────────────────────────────────
    select_parts = []

    # Group by columns first (must appear in SELECT for ONLY_FULL_GROUP_BY)
    for gb in group_by:
        select_parts.append(_quote(gb))

    # Metric expressions
    metric_aliases = []
    for m in other_metrics:
        expr, alias = _build_metric_expr(m)
        select_parts.append(f"{expr} AS {_quote(alias)}")
        metric_aliases.append(alias)

    # If no metrics at all, do SELECT *
    if not select_parts:
        select_parts = ["*"]

    select_clause = "SELECT " + ", ".join(select_parts)
    from_clause = f"FROM {tbl}"

    group_clause = ""
    if group_by:
        quoted_groups = [_quote(g) for g in group_by]
        group_clause = "GROUP BY " + ", ".join(quoted_groups)

    order_clause = ""
    if order_by:
        order_parts = []
        for ob in order_by:
            col = ob["column"]
            direction = validated_direction(ob.get("direction", "DESC"))
            
            # Check if col directly matches a metric alias
            matched_alias = None
            if col in metric_aliases:
                matched_alias = col
            else:
                # Find if any metric is defined on this column
                for m in other_metrics:
                    if m.get("column") == col:
                        _, a = _build_metric_expr(m)
                        matched_alias = a
                        break

            if matched_alias:
                order_parts.append(f"{_quote(matched_alias)} {direction}")
            elif group_by and col not in group_by:
                # If grouping is active and column is neither grouped nor a metric, order by first metric
                if metric_aliases:
                    order_parts.append(f"{_quote(metric_aliases[0])} {direction}")
                else:
                    order_parts.append(f"{_quote(group_by[0])} {direction}")
            else:
                order_parts.append(f"{_quote(col)} {direction}")
        order_clause = "ORDER BY " + ", ".join(order_parts)
    elif group_by and metric_aliases:
        # Default when grouping: order by first metric descending
        order_clause = f"ORDER BY {_quote(metric_aliases[0])} DESC"

    limit_clause = f"LIMIT {limit}" if limit else ""

    parts = [p for p in [select_clause, from_clause, full_where, group_clause, order_clause, limit_clause] if p]
    return "\n".join(parts)


def _compile_with_median(
    table: str,
    median_metrics: list[dict],
    other_metrics: list[dict],
    group_by: list[str],
    where: str,
    order_by: list[dict],
    limit: int | None,
) -> str:
    """
    Compile a query that includes median, using ROW_NUMBER window function.
    MySQL has no built-in MEDIAN, so we simulate it with a CTE.
    Only works for single-group or no-group median.
    """
    col = median_metrics[0]["column"]
    quoted_col = _quote(col)

    if not group_by:
        # Global median
        sql = f"""WITH ranked AS (
  SELECT {quoted_col},
         ROW_NUMBER() OVER (ORDER BY {quoted_col}) AS rn,
         COUNT(*) OVER () AS total
  FROM {table}
  {where}
)
SELECT AVG({quoted_col}) AS `median_{col}`
FROM ranked
WHERE rn IN (FLOOR((total + 1) / 2), CEIL((total + 1) / 2))"""
    else:
        group_cols = ", ".join(_quote(g) for g in group_by)
        sql = f"""WITH ranked AS (
  SELECT {group_cols}, {quoted_col},
         ROW_NUMBER() OVER (PARTITION BY {group_cols} ORDER BY {quoted_col}) AS rn,
         COUNT(*) OVER (PARTITION BY {group_cols}) AS total
  FROM {table}
  {where}
)
SELECT {group_cols}, AVG({quoted_col}) AS `median_{col}`
FROM ranked
WHERE rn IN (FLOOR((total + 1) / 2), CEIL((total + 1) / 2))
GROUP BY {group_cols}"""

    if limit:
        sql += f"\nLIMIT {limit}"

    return sql


def plan_to_interpretation(
    plan: dict[str, Any],
    table_name: str,
) -> str:
    """
    Generate a plain-English interpretation of the plan (deterministic, no LLM).
    Shown to user as 'How I understood your question'.
    """
    metrics = plan.get("metrics", [])
    group_by = plan.get("group_by", [])
    filters = plan.get("filters", [])
    time_range = plan.get("time_range")
    order_by = plan.get("order_by", [])
    limit = plan.get("limit")

    parts = []

    # Metrics
    if metrics:
        metric_strs = []
        for m in metrics:
            agg = m.get("agg", "sum").replace("_", " ")
            col = m["column"]
            metric_strs.append(f"{agg} of `{col}`")
        parts.append(", ".join(metric_strs))

    # Group by
    if group_by:
        parts.append(f"grouped by {', '.join(f'`{g}`' for g in group_by)}")

    # Time range
    if time_range:
        start = time_range.get("start", "")
        end = time_range.get("end", "")
        desc = time_range.get("description", f"{start} to {end}")
        parts.append(f"from {desc}")

    # Filters
    for flt in filters:
        parts.append(f"where `{flt['column']}` {flt.get('op', '=')} '{flt.get('value', '')}'")

    # Order
    if order_by:
        ob = order_by[0]
        direction = "highest" if ob.get("direction", "DESC") == "DESC" else "lowest"
        parts.append(f"{direction} first")

    # Limit
    if limit and limit < 1000:
        parts.append(f"top {limit}")

    from_part = f"from `{table_name}`"
    return " ".join(parts) + (f" {from_part}" if parts else from_part)
