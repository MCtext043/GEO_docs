from __future__ import annotations

from pathlib import Path


class ReportExportError(RuntimeError):
    pass


def export_txt(path: Path, text: str) -> Path:
    path = path.resolve()
    path.write_text(text, encoding="utf-8")
    return path


def export_md(path: Path, text: str) -> Path:
    path = path.resolve()
    path.write_text(text, encoding="utf-8")
    return path


def export_docx(path: Path, text: str) -> Path:
    try:
        import docx
    except ImportError as e:
        raise ReportExportError("Для экспорта в DOCX установите зависимость python-docx.") from e

    path = path.resolve()
    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    document.save(path)
    return path
