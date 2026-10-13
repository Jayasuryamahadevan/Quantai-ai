"""app/export/html_export.py"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import pandas as pd


async def export_html(df: pd.DataFrame, run_meta: dict[str, Any], path: Path) -> Path:
    """Export result as a styled standalone HTML file."""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>QuantAI AI Export</title>
        <style>
            body {{ font-family: system-ui, sans-serif; padding: 20px; color: #1e293b; }}
            h1 {{ color: #4f46e5; }}
            .meta-box {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
            th {{ background-color: #f1f5f9; font-weight: 600; }}
            tr:hover {{ background-color: #f8fafc; }}
        </style>
    </head>
    <body>
        <h1>QuantAI AI Analysis</h1>
        <div class="meta-box">
            <p><strong>Question:</strong> {run_meta.get('question', '')}</p>
            <p><strong>Insight:</strong> {run_meta.get('insight', '')}</p>
            <p><strong>Confidence:</strong> {run_meta.get('confidence', '')} | <strong>Verified:</strong> {'Yes' if run_meta.get('verified') else 'No'}</p>
        </div>
        <div>
            <h2>Data Result</h2>
            {df.to_html(index=False, classes='result-table')}
        </div>
    </body>
    </html>
    """
    path.write_text(html_content, encoding="utf-8")
    return path
