from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_LANGFLOW_API_KEY = "sk-ezs36Qqkpcs1Uw0Hak132-jiHd8597jTWwzTa4pGVVM"
DEFAULT_LANGFLOW_FLOW_ID = "62fc74d3-9edf-4d49-b702-51cfe82c976c"


@dataclass
class AppConfig:
    """Настройки подключения к Langflow и лимиты текста."""

    langflow_base_url: str = "http://127.0.0.1:7860"
    api_key: str = DEFAULT_LANGFLOW_API_KEY
    legacy_flow_id: str = DEFAULT_LANGFLOW_FLOW_ID
    mistral_api_key: str = ""
    flow_form_id: str = ""
    flow_fill_id: str = ""
    flow_verify_id: str = ""
    flow_rag_ingest_id: str = ""
    flow_rag_summary_id: str = ""
    rag_collection_name: str = "normdocs_documents"
    max_corpus_chars: int = 120_000
    max_data_chars: int = 120_000
    max_summary_chars: int = 200_000
    request_timeout_sec: int = 600

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            langflow_base_url=os.environ.get("LANGFLOW_BASE_URL", "http://127.0.0.1:7860").rstrip("/"),
            api_key=os.environ.get("LANGFLOW_API_KEY", DEFAULT_LANGFLOW_API_KEY),
            legacy_flow_id=os.environ.get("LANGFLOW_FLOW_ID", DEFAULT_LANGFLOW_FLOW_ID),
            mistral_api_key=os.environ.get("MISTRAL_API_KEY", ""),
            flow_form_id=os.environ.get("LANGFLOW_FLOW_FORM", ""),
            flow_fill_id=os.environ.get("LANGFLOW_FLOW_FILL", ""),
            flow_verify_id=os.environ.get("LANGFLOW_FLOW_VERIFY", ""),
            flow_rag_ingest_id=os.environ.get("LANGFLOW_FLOW_RAG_INGEST", ""),
            flow_rag_summary_id=os.environ.get("LANGFLOW_FLOW_RAG_SUMMARY", ""),
            rag_collection_name=os.environ.get("NORMDOCS_RAG_COLLECTION", "normdocs_documents"),
            max_corpus_chars=int(os.environ.get("NORMDOCS_MAX_CORPUS_CHARS", "120000")),
            max_data_chars=int(os.environ.get("NORMDOCS_MAX_DATA_CHARS", "120000")),
            max_summary_chars=int(os.environ.get("NORMDOCS_MAX_SUMMARY_CHARS", "200000")),
            request_timeout_sec=int(os.environ.get("NORMDOCS_REQUEST_TIMEOUT", "600")),
        )
