from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from normdocs_app.config import AppConfig
from normdocs_app.services.flow_resolve import discover_normdocs_flow_ids
from normdocs_app.services.langflow_client import LangflowClient, LangflowError


def _mock_response(json_data, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.text = str(json_data)
    r.json.return_value = json_data
    return r


def test_discover_normdocs_flow_ids_picks_triplet() -> None:
    flows = [
        {"id": "a", "name": "NormDocs — 1. Форма [abc12345]", "updated_at": "2025-01-02T00:00:00"},
        {"id": "b", "name": "NormDocs — 2. Заполнение [abc12345]", "updated_at": "2025-01-02T00:00:00"},
        {"id": "c", "name": "NormDocs — 3. Проверка [abc12345]", "updated_at": "2025-01-02T00:00:00"},
    ]
    cfg = AppConfig(langflow_base_url="http://127.0.0.1:7860", api_key="k")
    client = LangflowClient(cfg)
    client.session.get = MagicMock(return_value=_mock_response(flows))

    f1, f2, f3 = discover_normdocs_flow_ids(client)
    assert (f1, f2, f3) == ("a", "b", "c")


def test_discover_normdocs_flow_ids_empty_raises() -> None:
    cfg = AppConfig(langflow_base_url="http://127.0.0.1:7860", api_key="k")
    client = LangflowClient(cfg)
    client.session.get = MagicMock(return_value=_mock_response([]))

    with pytest.raises(LangflowError, match="пустой"):
        discover_normdocs_flow_ids(client)
