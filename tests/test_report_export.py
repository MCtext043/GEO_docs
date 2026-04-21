from __future__ import annotations

from pathlib import Path

from normdocs_app.services.report_export import export_docx, export_md, export_txt


def test_export_txt(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    export_txt(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"


def test_export_md(tmp_path: Path) -> None:
    p = tmp_path / "out.md"
    export_md(p, "# title")
    assert p.read_text(encoding="utf-8") == "# title"


def test_export_docx(tmp_path: Path) -> None:
    p = tmp_path / "out.docx"
    export_docx(p, "line1\nline2")
    assert p.is_file()
    assert p.stat().st_size > 0
