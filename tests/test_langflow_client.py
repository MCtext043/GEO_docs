from __future__ import annotations

from normdocs_app.services.langflow_client import parse_run_output


def test_parse_run_output_extracts_message_text() -> None:
    data = {
        "outputs": [
            {
                "outputs": [
                    {
                        "results": {
                            "message": {
                                "text": "Ответ модели",
                            }
                        }
                    }
                ]
            }
        ]
    }
    assert "Ответ модели" in parse_run_output(data)


def test_parse_run_output_fallback_json() -> None:
    data = {"outputs": []}
    out = parse_run_output(data)
    assert "outputs" in out or out == ""
