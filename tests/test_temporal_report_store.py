from pathlib import Path

import pytest

from app.orchestration.report_store import approved_report_path


def test_accepts_report_inside_export_root(tmp_path: Path):
    root = tmp_path / "exports"
    root.mkdir()
    report = root / "approved.pdf"
    report.write_bytes(b"%PDF-1.4")
    assert approved_report_path(str(report), root) == report.resolve()


def test_rejects_path_outside_export_root(tmp_path: Path):
    root = tmp_path / "exports"
    root.mkdir()
    other = tmp_path / "sensitive.pdf"
    other.write_bytes(b"not a report")
    with pytest.raises(ValueError):
        approved_report_path(str(other), root)


def test_rejects_symlinks_escaping_export_root(tmp_path: Path):
    root = tmp_path / "exports"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"data")
    shortcut = root / "linked.pdf"
    shortcut.symlink_to(outside)
    with pytest.raises(ValueError):
        approved_report_path(str(shortcut), root)


def test_rejects_nonreport_extensions_and_missing_files(tmp_path: Path):
    root = tmp_path / "exports"
    root.mkdir()
    bad = root / "secret.txt"
    bad.write_text("secret")
    with pytest.raises(ValueError):
        approved_report_path(str(bad), root)
    with pytest.raises(FileNotFoundError):
        approved_report_path(str(root / "missing.pdf"), root)
