from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

import requests

from normdocs_app.config import AppConfig


class LangflowError(RuntimeError):
    pass


def _walk_text(obj: Any, out: list[str]) -> None:
    if obj is None:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if s and len(s) > 2:
            out.append(s)
        return
    if isinstance(obj, dict):
        for k in ("text", "message", "content", "data", "result", "output"):
            if k in obj:
                _walk_text(obj[k], out)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _walk_text(v, out)
        return
    if isinstance(obj, list):
        for item in obj:
            _walk_text(item, out)


def parse_run_output(data: dict[str, Any]) -> str:
    """Достаёт человекочитаемый текст из ответа /api/v1/run/…"""
    texts: list[str] = []
    outputs = data.get("outputs") or []
    for block in outputs:
        _walk_text(block, texts)
    # Убираем дубликаты, сохраняя порядок
    seen: set[str] = set()
    uniq: list[str] = []
    for t in texts:
        key = t[:2000]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    return "\n\n---\n\n".join(uniq) if uniq else json.dumps(data, ensure_ascii=False, indent=2)[:50_000]


class LangflowClient:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "x-api-key": cfg.api_key,
            }
        )

    def run_flow(self, flow_id: str, input_value: str) -> str:
        flow_id = flow_id.strip()
        if not flow_id:
            raise LangflowError("Не указан ID потока Langflow (UUID).")
        base = self.cfg.langflow_base_url.rstrip("/") + "/"
        url = urljoin(base, f"api/v1/run/{flow_id}")
        body = {
            "input_value": input_value,
            "input_type": "chat",
            "output_type": "chat",
            "output_component": "",
            "tweaks": None,
            "session_id": None,
        }
        try:
            r = self.session.post(
                url,
                json=body,
                timeout=self.cfg.request_timeout_sec,
            )
        except requests.RequestException as e:
            raise LangflowError(f"Сеть / таймаут при вызове Langflow: {e}") from e
        if r.status_code == 401:
            raise LangflowError(
                "401 Unauthorized: проверьте API-ключ Langflow (заголовок x-api-key). "
                "Ключ создаётся в Langflow: Settings → API Keys."
            )
        if r.status_code == 404:
            raise LangflowError(
                f"404: поток не найден. URL={url} Проверьте UUID и что сервер запущен."
            )
        if not r.ok:
            raise LangflowError(f"HTTP {r.status_code}: {r.text[:2000]}")
        try:
            data = r.json()
        except json.JSONDecodeError as e:
            raise LangflowError(f"Не JSON в ответе: {r.text[:500]}") from e
        return parse_run_output(data)
