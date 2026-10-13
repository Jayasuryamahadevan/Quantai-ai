"""
app/agents/source_resolver.py — Resolves which data source and table to query.
Fetches the column catalog from the DB and populates state.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.graph.state import AgentState

log = logging.getLogger(__name__)


async def source_resolver_node(state: AgentState) -> dict[str, Any]:
    """
    Determine the active source and load its column catalog.
    """
    t0 = time.perf_counter()
    step = "source_resolver"

    source_id = state.get("source_id")

    try:
        from app.storage.models import Source, ColumnCatalog
        from app.storage.database import app_session
        from sqlalchemy import select

        with app_session() as session:
            if source_id:
                src = session.get(Source, source_id)
            else:
                # Get most recently active source
                src = session.execute(
                    select(Source).where(Source.is_active == True).order_by(Source.updated_at.desc()).limit(1)
                ).scalar_one_or_none()

            if not src:
                elapsed = int((time.perf_counter() - t0) * 1000)
                return {
                    "errors": state.get("errors", []) + ["No active data source found. Please connect or upload a data source."],
                    "current_step": step,
                    "trace": state.get("trace", []) + [{"step": step, "status": "error", "duration_ms": elapsed}],
                }

            # Load catalog
            catalog_rows = session.execute(
                select(ColumnCatalog)
                .where(ColumnCatalog.source_id == src.id)
                .order_by(ColumnCatalog.ordinal_position)
            ).scalars().all()

            catalog = [
                {
                    "safe_name": c.safe_name,
                    "original_name": c.original_name,
                    "col_type": c.col_type,
                    "mysql_type": c.mysql_type,
                    "null_pct": c.null_pct,
                    "distinct_count": c.distinct_count,
                    "col_min": c.col_min,
                    "col_max": c.col_max,
                    "top_values": c.top_values or [],
                    "description": c.description or "",
                    "unit": c.unit or "",
                    "synonyms": c.synonyms or [],
                    "is_date_col": c.is_date_col,
                    "is_key_col": c.is_key_col,
                    "is_pii": c.is_pii,
                }
                for c in catalog_rows
            ]

            catalog_map = {c["safe_name"]: c for c in catalog}

            selected_source_dict = {
                "id": src.id,
                "name": src.name,
                "source_type": src.source_type,
                "table_name": src.table_name,
                "schema_name": src.schema_name,
                "row_count": src.row_count,
                "col_count": src.col_count,
            }
            src_id = src.id
            src_table_name = src.table_name
            src_schema_name = src.schema_name
            src_name = src.name
            src_row_count = src.row_count

        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "selected_source": selected_source_dict,
            "source_id": src_id,
            "table_name": src_table_name,
            "schema_name": src_schema_name or "quantai_data",
            "full_catalog": catalog,
            "column_catalog_map": catalog_map,
            "current_step": step,
            "trace": state.get("trace", []) + [{
                "step": step,
                "status": "completed",
                "duration_ms": elapsed,
                "source": src_name,
                "columns": len(catalog),
                "rows": src_row_count,
            }],
        }

    except Exception as exc:
        log.exception("Source resolver error")
        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "errors": state.get("errors", []) + [f"Source resolver failed: {exc}"],
            "current_step": step,
            "trace": state.get("trace", []) + [{"step": step, "status": "error", "duration_ms": elapsed, "error": str(exc)}],
        }
