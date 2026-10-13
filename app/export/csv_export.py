"""app/export/csv_export.py"""
from __future__ import annotations
from pathlib import Path
import pandas as pd


async def export_csv(df: pd.DataFrame, path: Path) -> Path:
    """Export DataFrame as UTF-8 BOM CSV (opens correctly in Excel)."""
    df.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",  # UTF-8 with BOM
        quoting=1,  # QUOTE_ALL to prevent formula injection
    )
    return path
