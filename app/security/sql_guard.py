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

    # Parse the original SQL: removing comments and splitting on semicolons
    # can corrupt quoted values and miss statements.
    try:
        statements = sqlglot.parse(raw, dialect="mysql")
    except ParseError as exc:
        return GuardResult(
            valid=False,
            sql=raw,
            error=f"SQL parse error: {exc}",
        )

    if len(statements) != 1 or statements[0] is None:
        return GuardResult(
            valid=False,
            sql=raw,
            error="Exactly one SELECT statement is required.",
        )

    stmt = statements[0]

    # ── 5. Allow only SELECT (or WITH … SELECT) ──────────────────────────────
    if not isinstance(stmt, (exp.Select, exp.With)):
        return GuardResult(
            valid=False,
            sql=raw,
            error=f"Only SELECT statements are allowed. Got: {type(stmt).__name__}.",
        )

    # Restrict every nested operation; SELECT can contain unsafe subexpressions.
    forbidden_nodes = {
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "TruncateTable",
        "Command", "Into", "Merge", "Copy", "LoadData", "Grant", "Revoke",
    }
    for node in stmt.walk():
        if type(node).__name__ in forbidden_nodes:
            return GuardResult(False, raw, "Unsafe SQL operation rejected")
        if isinstance(node, exp.Func):
            func_name = str(getattr(node, "name", "") or "").upper()
            if func_name in {"SLEEP", "BENCHMARK", "LOAD_FILE", "GET_LOCK", "RELEASE_LOCK"}:
                return GuardResult(False, raw, f"Unsafe SQL function rejected: {func_name}")

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

        # Resolve aliases before validating qualified columns.
        aliases: dict[str, str] = {}
        for table_node in stmt.find_all(exp.Table):
            tbl = table_node.name.lower().strip("`")
            if tbl and tbl not in known_upper and tbl not in cte_names:
                hallucinated_tables.append(tbl)
            elif tbl in known_upper:
                aliases[table_node.alias_or_name.lower().strip("`")] = tbl

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
                real_table = aliases.get(table_ref, table_ref)
                if real_table in known_upper and col_name not in known_upper[real_table] and col_name not in defined_aliases:
                    hallucinated_columns.append(f"{table_ref}.{col_name}")
                elif real_table not in known_upper:
                    hallucinated_columns.append(f"Unknown table qualifier: {table_ref}")
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

    # Enforce an outermost row bound, including queries with existing LIMIT.
    if isinstance(default_limit, bool) or not isinstance(default_limit, int) or default_limit < 1:
        return GuardResult(False, raw, "Default row limit must be positive")
    limit_node = stmt.args.get("limit")
    if limit_node is None:
        warnings.append(f"No LIMIT clause found — adding LIMIT {default_limit}.")
        stmt.set("limit", exp.Limit(expression=exp.Literal.number(default_limit)))
    else:
        literal = limit_node.args.get("expression")
        if not isinstance(literal, exp.Literal) or literal.is_string or not literal.this.isdigit():
            return GuardResult(False, raw, "LIMIT must be a positive integer literal")
        requested_limit = int(literal.this)
        if requested_limit < 1:
            return GuardResult(False, raw, "LIMIT must be a positive integer")
        if requested_limit > default_limit:
            warnings.append(f"LIMIT reduced from {requested_limit} to {default_limit}.")
            limit_node.set("expression", exp.Literal.number(default_limit))

    safe_sql = stmt.sql(dialect="mysql")

    log.debug("sql_guard: PASSED — %s", safe_sql[:120])
    return GuardResult(valid=True, sql=safe_sql, warnings=warnings)
