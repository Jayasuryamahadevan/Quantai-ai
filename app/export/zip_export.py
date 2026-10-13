"""app/export/zip_export.py"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import zipfile
import json
import pandas as pd
from app.export.csv_export import export_csv
from app.export.excel_export import export_excel


async def export_zip(df: pd.DataFrame, run_meta: dict[str, Any], run_id: str, export_dir: Path, base_name: str) -> Path:
    """Export everything into a ZIP file."""
    zip_path = export_dir / f"{base_name}.zip"
    
    csv_path = export_dir / f"{base_name}.csv"
    await export_csv(df, csv_path)
    
    xlsx_path = export_dir / f"{base_name}.xlsx"
    await export_excel(df, run_meta, xlsx_path)
    
    json_path = export_dir / f"{base_name}.json"
    json_path.write_text(json.dumps(run_meta, indent=2, default=str), encoding="utf-8")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(csv_path, f"{base_name}.csv")
        zipf.write(xlsx_path, f"{base_name}.xlsx")
        zipf.write(json_path, f"{base_name}_meta.json")
        
    csv_path.unlink(missing_ok=True)
    xlsx_path.unlink(missing_ok=True)
    json_path.unlink(missing_ok=True)
    
    return zip_path
