"""Опциональные проверки живого Langflow.

Загружаем `.env` из корня проекта здесь же (до любых проверок), чтобы не зависеть
от порядка импорта conftest и от момента вычисления @pytest.mark.skipif.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)


def _base_url() -> str:
    return os.environ.get("LANGFLOW_BASE_URL", "http://127.0.0.1:7860").rstrip("/")


def _require_api_key() -> str:
    key = (os.environ.get("LANGFLOW_API_KEY") or "").strip()
    if not key:
        pytest.skip(
            f"Нет LANGFLOW_API_KEY. Файл: {_ENV_FILE} (есть на диске: {_ENV_FILE.is_file()}). "
            "Добавьте в .env строку LANGFLOW_API_KEY=sk-... без пробелов вокруг = и без кавычек."
        )
    return key


@pytest.mark.live_langflow
def test_langflow_version_authenticated() -> None:
    key = _require_api_key()
    r = requests.get(
        f"{_base_url()}/api/v1/version",
        headers={"x-api-key": key, "accept": "application/json"},
        timeout=15,
    )
    assert r.ok, r.text
    data = r.json()
    assert "version" in data or "main_version" in data


@pytest.mark.live_langflow
def test_langflow_flows_list() -> None:
    key = _require_api_key()
    r = requests.get(
        f"{_base_url()}/api/v1/flows/",
        headers={"x-api-key": key, "accept": "application/json"},
        params={
            "get_all": "true",
            "remove_example_flows": "false",
            "components_only": "false",
            "header_flows": "false",
        },
        timeout=120,
    )
    assert r.ok, r.text[:500]
    assert r.json() is not None


def test_langflow_health_unauthenticated() -> None:
    """Обычно доступен без ключа."""
    try:
        r = requests.get(f"{_base_url()}/health", timeout=5)
    except requests.RequestException as e:
        pytest.skip(f"Langflow недоступен: {e}")
    assert r.status_code == 200
