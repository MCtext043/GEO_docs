"""Общие фикстуры: подхватываем .env из корня проекта (как в normdocs_app.main)."""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# До сбора тестов: @pytest.mark.skipif(...) в модулях смотрит os.environ раньше,
# чем успевает отработать session-фикстура — поэтому .env грузим при импорте conftest.
load_dotenv(PROJECT_ROOT / ".env")


@pytest.fixture(scope="session", autouse=True)
def _load_dotenv_again() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT
