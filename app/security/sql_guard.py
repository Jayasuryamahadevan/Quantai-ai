"""
app/security/sql_guard.py — SQL validation before execution.

All generated SQL MUST pass through this guard. It:
  1. Parses SQL with sqlglot (mysql dialect)
  2. Allows only SELECT / WITH…SELECT statements
  3. Rejects dangerous keywords and multi-statement input
  4. Validates every table and column against the known schema
  5. Auto-adds LIMIT if missing
  6. Returns a detailed error message for the retry loop
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import sqlglot
import sqlglot.expressions as exp
from sqlglot.errors import ParseError

log = logging.getLogger(__name__)

# Keywords that must never appear in generated SQL
FORBIDDEN_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL",
    "LOAD", "IMPORT", "OUTFILE", "DUMPFILE", "INTO OUTFILE",
    "ATTACH", "DETACH",
})

# Regex patterns to catch smuggled statements via comments
_COMMENT_STRIP = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)
_SEMICOLON = re.compile(r";")


@dataclass
class GuardResult:
    valid: bool
    sql: str                    # normalised SQL (or original if invalid)
    error: Optional[str] = None
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def validate_sql(
    sql: str,
    known_tables: Optional[dict[str, list[str]]] = None,
    default_limit: int = 1000,
) -> GuardResult:
    """
    Validate and normalise a SQL string.

    Args:
        sql: The raw SQL from the model.
        known_tables: Dict mapping table_name -> list[column_names].
            If provided, table/column existence is checked.
        default_limit: Added if the query has no LIMIT clause.

    Returns:
        GuardResult with valid=True and the (possibly amended) SQL,
        or valid=False and a descriptive error message.
    """
    raw = sql.strip()

    # ── 1. Strip dangerous comment patterns ─────────────────────────────────
    stripped = _COMMENT_STRIP.sub(" ", raw)

    # ── 2. Detect multiple statements (semicolon separation) ─────────────────
    # Allow a trailing semicolon but not mid-query ones
    parts = [p.strip() for p in _SEMICOLON.split(stripped) if p.strip()]
    if len(parts) > 1:
        return GuardResult(
            valid=False,
            sql=raw,
            error="Multi-statement SQL rejected. Only a single SELECT is allowed.",
        )

    # ── 3. Check for forbidden keywords (case-insensitive) ───────────────────
    upper = stripped.upper()
    for kw in FORBIDDEN_KEYWORDS:
        # Use word-boundary check to avoid false positives inside column names
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, upper):
            return GuardResult(
                valid=False,
                sql=raw,
                error=f"Forbidden keyword detected: {kw}. Only SELECT statements are allowed.",
            )

    # ── 4. Parse with sqlglot ────────────────────────────────────────────────
    try:
        statements = sqlglot.parse(stripped, dialect="mysql")
    except ParseError as exc:
        return GuardResult(
            valid=False,
            sql=raw,
            error=f"SQL parse error: {exc}",
        )

    if not statements or statements[0] is None:
        return GuardResult(
            valid=False,
            sql=raw,
            error="Could not parse SQL statement.",
        )

    stmt = statements[0]

    # ── 5. Allow only SELECT (or WITH … SELECT) ──────────────────────────────
    if not isinstance(stmt, (exp.Select, exp.With)):
        return GuardResult(
            valid=False,
            sql=raw,
            error=f"Only SELECT statements are allowed. Got: {type(stmt).__name__}.",
        )

    # For WITH statements, ensure the final statement is a SELECT
    if isinstance(stmt, exp.With):
        inner = stmt.find(exp.Select)
        if inner is None:
            return GuardResult(
                valid=False,
                sql=raw,
                error="WITH clause must end with a SELECT statement.",
            )

    # ── 6. Table and column validation ───────────────────────────────────────
    warnings: list[str] = []
    hallucinated_tables: list[str] = []
    hallucinated_columns: list[str] = []

    if known_tables:
        known_upper = {t.lower(): [c.lower() for c in cols] for t, cols in known_tables.items()}

        # Collect CTE names (e.g. WITH ranked AS ...)
        cte_names = {
            cte.alias_or_name.lower().strip("`")
            for cte in stmt.find_all(exp.CTE)
            if cte.alias_or_name
        }

        # Collect defined column/expression aliases (e.g. SELECT expr AS alias)
        defined_aliases = {
            alias_node.alias.lower().strip("`")
            for alias_node in stmt.find_all(exp.Alias)
            if alias_node.alias
        }

        # Extract referenced tables
        for table_node in stmt.find_all(exp.Table):
            tbl = table_node.name.lower().strip("`")
            if tbl and tbl not in known_upper and tbl not in cte_names:
                hallucinated_tables.append(tbl)

        if hallucinated_tables:
            return GuardResult(
                valid=False,
                sql=raw,
                error=(
                    f"Hallucinated table(s): {hallucinated_tables}. "
                    f"Known tables: {list(known_upper.keys())}. "
                    "Use only the tables listed in the schema."
                ),
            )

        # Validate columns (only when we know which table columns are)
        for col_node in stmt.find_all(exp.Column):
            col_name = col_node.name.lower().strip("`")
            table_ref = col_node.table
            if table_ref:
                table_ref = table_ref.lower().strip("`")
                if table_ref in cte_names:
                    continue
                if table_ref in known_upper and col_name not in known_upper[table_ref] and col_name not in defined_aliases:
                    hallucinated_columns.append(f"{table_ref}.{col_name}")
            else:
                # Check across all tables and defined aliases
                all_cols = [c for cols in known_upper.values() for c in cols]
                if col_name and col_name != "*" and col_name not in all_cols and col_name not in defined_aliases:
                    hallucinated_columns.append(col_name)

        if hallucinated_columns:
            all_col_list = sorted({c for cols in known_upper.values() for c in cols})
            return GuardResult(
                valid=False,
                sql=raw,
                error=(
                    f"Unknown column(s): {hallucinated_columns}. "
                    f"Available columns include: {all_col_list[:30]}. "
                    "Use only column names from the schema."
                ),
            )

    # ── 7. Auto-add LIMIT ────────────────────────────────────────────────────
    # Find the outermost SELECT to check / add LIMIT
    select_node = stmt.find(exp.Select)
    limit_node = stmt.find(exp.Limit)

    if select_node and limit_node is None:
        warnings.append(f"No LIMIT clause found — adding LIMIT {default_limit}.")
        # Re-generate with LIMIT appended
        safe_sql = stripped.rstrip(";") + f"\nLIMIT {default_limit}"
    else:
        safe_sql = stripped.rstrip(";")

    # ── 8. Normalise (pretty-print through sqlglot) ──────────────────────────
    try:
        safe_sql = sqlglot.transpile(safe_sql, read="mysql", write="mysql", pretty=False)[0]
    except Exception:
        # Keep original if transpile fails
        pass

    log.debug("sql_guard: PASSED — %s", safe_sql[:120])
    return GuardResult(valid=True, sql=safe_sql, warnings=warnings)
