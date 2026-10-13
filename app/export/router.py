"""
app/export/router.py — Route export requests to format-specific handlers.
All exports are generated locally; nothing leaves the machine.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

log = logging.getLogger(__name__)


async def handle_export(run_id: str, format: str) -> FileResponse:
    """Route to the appropriate export handler."""
    from app.storage.models import QueryRun, Source
    from app.storage.database import app_session, readonly_session
    from app.config import get_settings
    import pandas as pd
    from sqlalchemy import text

    cfg = get_settings()
    valid_formats = ("csv", "xlsx", "pdf", "html", "png", "svg", "json", "zip")
    if format not in valid_formats:
        raise HTTPException(400, f"Invalid format. Choose from: {valid_formats}")

    # Load run and result
    with app_session() as session:
        run = session.get(QueryRun, run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        src = session.get(Source, run.source_id) if run.source_id else None
        # Copy ORM fields while the session is still open. SQLAlchemy expires
        # these objects when the session closes; using them later caused every
        # download request to fail with DetachedInstanceError.
        run_record = {
            "generated_sql": run.generated_sql,
            "question": run.question,
            "insight": run.insight_text,
            "confidence": run.confidence,
            "verified": run.verified,
            "interpretation": run.interpretation_text,
            "columns_used": run.columns_used or [],
            "resolved_dates": run.resolved_date_range,
            "source_name": src.name if src else "data",
        }

    if not run_record["generated_sql"]:
        raise HTTPException(400, "No SQL available for this run")

    # Re-execute without display limit for full export
    export_sql = _remove_limit(run_record["generated_sql"], cfg.max_export_rows)

    try:
        with readonly_session() as conn:
            df = pd.read_sql(text(export_sql), conn)
    except Exception as exc:
        raise HTTPException(500, f"Export query failed: {exc}")

    # Source name for filename
    source_name = run_record["source_name"]
    from slugify import slugify
    question_slug = slugify(run_record["question"][:40], separator="_")
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    base_name = f"quantai_{slugify(source_name, separator='_')[:20]}_{question_slug}_{ts}"

    export_dir = cfg.exports_dir
    export_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "question": run_record["question"],
        "insight": run_record["insight"],
        "sql": run_record["generated_sql"],
        "confidence": run_record["confidence"],
        "verified": run_record["verified"],
        "interpretation": run_record["interpretation"],
        "columns_used": run_record["columns_used"],
        "resolved_dates": run_record["resolved_dates"],
    }

    if format == "csv":
        from app.export.csv_export import export_csv
        path = await export_csv(df, export_dir / f"{base_name}.csv")

    elif format == "xlsx":
        from app.export.excel_export import export_excel
        path = await export_excel(df, run_meta, export_dir / f"{base_name}.xlsx")

    elif format == "pdf":
        from app.export.pdf_export import export_pdf
        path = await export_pdf(df, run_meta, export_dir / f"{base_name}.pdf")

    elif format == "html":
        from app.export.html_export import export_html
        path = await export_html(df, run_meta, export_dir / f"{base_name}.html")

    elif format in ("png", "svg"):
        from app.export.chart_export import export_chart
        path = await export_chart(run_id, format, export_dir / f"{base_name}.{format}")

    elif format == "json":
        from app.export.json_export import export_json
        path = await export_json(df, run_meta, export_dir / f"{base_name}.json")

    elif format == "zip":
        from app.export.zip_export import export_zip
        path = await export_zip(df, run_meta, run_id, export_dir, base_name)

    else:
        raise HTTPException(400, "Unknown format")

    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type=_media_type(format),
    )


def _remove_limit(sql: str, max_rows: int) -> str:
    """Remove or replace LIMIT clause for full export."""
    import re
    # Replace existing LIMIT with max_export_rows
    sql = re.sub(r"\bLIMIT\s+\d+\b", f"LIMIT {max_rows}", sql, flags=re.IGNORECASE)
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + f"\nLIMIT {max_rows}"
    return sql


def _media_type(format: str) -> str:
    mapping = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "html": "text/html",
        "png": "image/png",
        "svg": "image/svg+xml",
        "json": "application/json",
        "zip": "application/zip",
    }
    return mapping.get(format, "application/octet-stream")
