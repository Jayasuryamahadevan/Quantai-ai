"""app/export/json_export.py"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import pandas as pd


async def export_json(df: pd.DataFrame, run_meta: dict[str, Any], path: Path) -> Path:
    """Export result as JSON."""
    data = {
        "metadata": run_meta,
        "data": df.to_dict(orient="records")
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
