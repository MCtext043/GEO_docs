from __future__ import annotations

from pathlib import Path

import pytest

from normdocs_app.services.document_text import collect_corpus, extract_file_text


def test_extract_txt_utf8(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("Привет, корпус.", encoding="utf-8")
    assert "корпус" in extract_file_text(p)


def test_collect_corpus_with_progress(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_text("x" * 100, encoding="utf-8")
    (tmp_path / "two.txt").write_text("y" * 100, encoding="utf-8")
    logs: list[str] = []

    text, used = collect_corpus(tmp_path, 10_000, on_progress=logs.append)

    assert len(used) == 2
    assert "x" * 50 in text
    assert any("Итого" in line for line in logs)
