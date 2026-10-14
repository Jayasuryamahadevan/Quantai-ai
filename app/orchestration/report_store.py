"""Resolve approved immutable report artifacts within the configured export root."""
from __future__ import annotations

from pathlib import Path


def approved_report_path(file_path: str, export_root: Path) -> Path:
    """Fail closed for missing files and anything outside the export directory."""
    root = export_root.resolve(strict=True)
    report = Path(file_path).resolve(strict=True)
    if not report.is_relative_to(root):
        raise ValueError("Report artifact path is outside the export directory")
    if not report.is_file() or report.suffix.lower() not in {".pdf", ".xlsx", ".csv"}:
        raise ValueError("Unsupported or missing report artifact")
    return report
