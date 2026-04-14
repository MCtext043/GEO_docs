from __future__ import annotations

from normdocs_app.services.payloads import (
    payload_fill_template,
    payload_form_from_normatives,
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
