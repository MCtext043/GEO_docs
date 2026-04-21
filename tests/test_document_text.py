from __future__ import annotations

from pathlib import Path

import pytest

import normdocs_app.services.document_text as document_text
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


def test_extract_rar_dispatches_to_archive_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "sample.rar"
    p.write_bytes(b"not_real_rar")

    called = {"ok": False}

    def _fake_extract(path: Path) -> str:
        called["ok"] = True
        assert path == p
        return "archive text"

    monkeypatch.setattr(document_text, "_extract_rar_text", _fake_extract)

    out = extract_file_text(p)
    assert called["ok"] is True
    assert out == "archive text"


def test_extract_image_dispatches_to_ocr_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "scan.png"
    p.write_bytes(b"fake_png")

    called = {"ok": False}

    def _fake_read(path: Path) -> str:
        called["ok"] = True
        assert path == p
        return "ocr text"

    monkeypatch.setattr(document_text, "_read_image", _fake_read)

    out = extract_file_text(p)
    assert called["ok"] is True
    assert out == "ocr text"
