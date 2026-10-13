"""app/export/excel_export.py — Excel workbook with multiple formatted sheets."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import pandas as pd
import xlsxwriter


async def export_excel(df: pd.DataFrame, run_meta: dict[str, Any], path: Path) -> Path:
    """Create a formatted Excel workbook with Answer, Result, Method sheets."""
    workbook = xlsxwriter.Workbook(str(path))

    # Formats
    bold = workbook.add_format({"bold": True, "font_color": "#1e293b"})
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#6366f1", "font_color": "white",
        "border": 1, "text_wrap": True,
    })
    num_fmt = workbook.add_format({"num_format": "#,##0.00"})
    int_fmt = workbook.add_format({"num_format": "#,##0"})
    date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
    footer_fmt = workbook.add_format({"italic": True, "font_color": "#64748b", "font_size": 9})

    # ── Sheet 1: Answer ──────────────────────────────────────────────────────
    ws_ans = workbook.add_worksheet("Answer")
    ws_ans.set_column(0, 0, 20)
    ws_ans.set_column(1, 1, 80)
    rows = [
        ("Question", run_meta.get("question", "")),
        ("Answer", run_meta.get("insight", "")),
        ("Confidence", run_meta.get("confidence", "")),
        ("Verified", "Yes" if run_meta.get("verified") else "No"),
        ("Resolved Dates", run_meta.get("resolved_dates", "")),
        ("Interpretation", run_meta.get("interpretation", "")),
        ("Columns Used", ", ".join(run_meta.get("columns_used", []))),
        ("Generated at", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")),
        ("Data source", "QuantAI AI — local analysis"),
    ]
    for r, (label, value) in enumerate(rows):
        ws_ans.write(r, 0, label, bold)
        ws_ans.write(r, 1, str(value))
    ws_ans.write(len(rows) + 1, 0, "Generated locally by QuantAI AI", footer_fmt)

    # ── Sheet 2: Result ──────────────────────────────────────────────────────
    ws_res = workbook.add_worksheet("Result")
    # Write header
    for col_idx, col_name in enumerate(df.columns):
        ws_res.write(0, col_idx, col_name, header_fmt)
    # Auto-fit column widths
    for col_idx, col_name in enumerate(df.columns):
        max_len = max(len(str(col_name)), df[col_name].astype(str).str.len().max() if len(df) > 0 else 10)
        ws_res.set_column(col_idx, col_idx, min(int(max_len * 1.2), 50))

    # Write data with formula injection prevention
    for r_idx, (_, row) in enumerate(df.iterrows()):
        for col_idx, (col_name, value) in enumerate(row.items()):
            safe_value = _sanitize_cell(value)
            if isinstance(safe_value, float):
                ws_res.write_number(r_idx + 1, col_idx, safe_value, num_fmt)
            elif isinstance(safe_value, int):
                ws_res.write_number(r_idx + 1, col_idx, safe_value, int_fmt)
            else:
                ws_res.write(r_idx + 1, col_idx, safe_value)

    ws_res.freeze_panes(1, 0)
    ws_res.autofilter(0, 0, len(df), len(df.columns) - 1)

    # ── Sheet 3: Method ──────────────────────────────────────────────────────
    ws_meth = workbook.add_worksheet("Method")
    ws_meth.set_column(0, 0, 25)
    ws_meth.set_column(1, 1, 100)
    method_rows = [
        ("How understood", run_meta.get("interpretation", "")),
        ("SQL Query", run_meta.get("sql", "")),
        ("Confidence", run_meta.get("confidence", "")),
        ("Verified by Pandas", "Yes" if run_meta.get("verified") else "No"),
    ]
    for r, (label, value) in enumerate(method_rows):
        ws_meth.write(r, 0, label, bold)
        ws_meth.write(r, 1, str(value))

    workbook.close()
    return path


def _sanitize_cell(value: Any) -> Any:
    """Prevent CSV/Excel formula injection."""
    if isinstance(value, str):
        if value.startswith(("=", "+", "-", "@")):
            return "'" + value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return value
