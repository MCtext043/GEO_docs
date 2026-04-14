from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    """Настройки подключения к Langflow и лимиты текста."""

    langflow_base_url: str = "http://127.0.0.1:7860"
    api_key: str = ""
    flow_form_id: str = ""
    flow_fill_id: str = ""
    flow_verify_id: str = ""
    max_corpus_chars: int = 120_000
    max_data_chars: int = 120_000
    request_timeout_sec: int = 600

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            langflow_base_url=os.environ.get("LANGFLOW_BASE_URL", "http://127.0.0.1:7860").rstrip("/"),
            api_key=os.environ.get("LANGFLOW_API_KEY", ""),
            flow_form_id=os.environ.get("LANGFLOW_FLOW_FORM", ""),
            flow_fill_id=os.environ.get("LANGFLOW_FLOW_FILL", ""),
            flow_verify_id=os.environ.get("LANGFLOW_FLOW_VERIFY", ""),
            max_corpus_chars=int(os.environ.get("NORMDOCS_MAX_CORPUS_CHARS", "120000")),
            max_data_chars=int(os.environ.get("NORMDOCS_MAX_DATA_CHARS", "120000")),
            request_timeout_sec=int(os.environ.get("NORMDOCS_REQUEST_TIMEOUT", "600")),
        )
