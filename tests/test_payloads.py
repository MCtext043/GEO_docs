from __future__ import annotations

from normdocs_app.services.payloads import (
    payload_direct_summary,
    payload_fill_template,
    payload_form_from_normatives,
    payload_rag_ingest,
    payload_rag_summary,
    payload_verify,
)


def test_payload_form_contains_normative_block() -> None:
    p = payload_form_from_normatives("статья 1")
    assert "НОРМАТИВНЫЕ" in p
    assert "статья 1" in p


def test_payload_fill_contains_both_blocks() -> None:
    p = payload_fill_template("форма", "данные")
    assert "форма" in p
    assert "данные" in p


def test_payload_verify_contains_report() -> None:
    p = payload_verify("норма", "отчёт")
    assert "норма" in p
    assert "отчёт" in p


def test_payload_rag_ingest_contains_collection_and_docs() -> None:
    p = payload_rag_ingest("my_docs", "текст документа")
    assert "RAG_INGEST" in p
    assert "my_docs" in p
    assert "текст документа" in p


def test_payload_rag_summary_contains_collection() -> None:
    p = payload_rag_summary("my_docs")
    assert "RAG_SUMMARY" in p
    assert "my_docs" in p


def test_payload_direct_summary_contains_documents() -> None:
    p = payload_direct_summary("файл 1: текст")
    assert "суммаризируй" in p
    assert "файл 1: текст" in p
