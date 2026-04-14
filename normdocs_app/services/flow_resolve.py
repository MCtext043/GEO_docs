"""Поиск UUID трёх потоков NormDocs через GET /api/v1/flows/.

Ожидаются потоки, созданные кнопкой «Создать три потока в Langflow (API)»:
имена начинаются с «NormDocs — 1.», «NormDocs — 2.», «NormDocs — 3.».
При нескольких наборах выбирается набор с максимальным временем обновления.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests

from normdocs_app.config import AppConfig
from normdocs_app.services.langflow_client import LangflowClient, LangflowError

# Должны совпадать с префиксами имён в flow_provision.provision_normdocs_flows
_STEP_PREFIXES: tuple[tuple[int, str], ...] = (
    (1, "NormDocs — 1."),
    (2, "NormDocs — 2."),
    (3, "NormDocs — 3."),
)

_SUFFIX_RE = re.compile(r"\[([a-f0-9]{8})\]\s*$")


def _flow_base_url(cfg: AppConfig) -> str:
    return cfg.langflow_base_url.rstrip("/") + "/"


def _parse_updated_at(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return 0.0
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            if fmt.endswith("%z") and len(s) > 5 and (s[-6] in "+-" or s.endswith("Z")):
                ss = s.replace("Z", "+00:00")
                return datetime.fromisoformat(ss).timestamp()
            return datetime.fromisoformat(s).timestamp()
        except ValueError:
            continue
    return 0.0


def _list_flows_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "flows", "data"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    return []


def _flow_step_from_name(name: str) -> tuple[int | None, str]:
    """Возвращает (номер шага 1..3, суффикс из [xxxxxxxx] или '')."""
    for step, prefix in _STEP_PREFIXES:
        if name.startswith(prefix):
            m = _SUFFIX_RE.search(name)
            suffix = m.group(1) if m else ""
            return step, suffix
    return None, ""


def discover_normdocs_flow_ids(client: LangflowClient) -> tuple[str, str, str]:
    """Возвращает (flow_form_id, flow_fill_id, flow_verify_id)."""
    url = urljoin(_flow_base_url(client.cfg), "api/v1/flows/")
    params = {
        "get_all": "true",
        "remove_example_flows": "false",
        "components_only": "false",
        "header_flows": "false",
    }
    try:
        r = client.session.get(url, params=params, timeout=120)
    except requests.RequestException as e:
        raise LangflowError(f"Сеть при запросе списка потоков: {e}") from e
    if r.status_code == 401:
        raise LangflowError("401 при списке потоков — проверьте API-ключ Langflow.")
    if not r.ok:
        raise LangflowError(f"Список потоков: HTTP {r.status_code}: {r.text[:2000]}")
    try:
        raw = r.json()
    except json.JSONDecodeError as e:
        raise LangflowError(f"Список потоков: не JSON: {r.text[:500]}") from e

    flows = _list_flows_payload(raw)
    if not flows:
        raise LangflowError(
            "Сервер вернул пустой список потоков. Создайте три потока кнопкой "
            "«Создать три потока в Langflow (API)» на вкладке «Настройки»."
        )

    # Группируем по суффиксу [xxxxxxxx]: один набор = три шага с одним суффиксом
    groups: dict[str, dict[int, dict[str, Any]]] = {}
    for f in flows:
        name = (f.get("name") or "").strip()
        step, suffix = _flow_step_from_name(name)
        if step is None:
            continue
        key = suffix if suffix else "_legacy"
        groups.setdefault(key, {})[step] = f

    complete: list[tuple[str, dict[int, dict[str, Any]]]] = [
        (k, g) for k, g in groups.items() if set(g.keys()) == {1, 2, 3}
    ]
    if not complete:
        raise LangflowError(
            "На сервере не найден полный набор из трёх потоков NormDocs (имена должны начинаться с "
            "«NormDocs — 1.», «NormDocs — 2.», «NormDocs — 3.»). "
            "Нажмите «Создать три потока в Langflow (API)» или проверьте имена в веб-интерфейсе Langflow."
        )

    def group_score(g: dict[int, dict[str, Any]]) -> float:
        return max(_parse_updated_at(g[s].get("updated_at")) for s in (1, 2, 3))

    _, best = max(complete, key=lambda item: group_score(item[1]))

    def fid(step: int) -> str:
        x = best[step].get("id")
        if not x:
            raise LangflowError(f"У потока шага {step} нет поля id в ответе API.")
        return str(x)

    return fid(1), fid(2), fid(3)


def resolve_normdocs_flow_ids(cfg: AppConfig) -> AppConfig:
    """
    Если в cfg или в переменных окружения уже заданы все три UUID — возвращает cfg без запросов.
    Иначе запрашивает список потоков и подставляет идентификаторы NormDocs.
    """
    if (cfg.flow_form_id or "").strip() and (cfg.flow_fill_id or "").strip() and (cfg.flow_verify_id or "").strip():
        return cfg

    e1 = (os.environ.get("LANGFLOW_FLOW_FORM") or "").strip()
    e2 = (os.environ.get("LANGFLOW_FLOW_FILL") or "").strip()
    e3 = (os.environ.get("LANGFLOW_FLOW_VERIFY") or "").strip()
    if e1 and e2 and e3:
        return replace(cfg, flow_form_id=e1, flow_fill_id=e2, flow_verify_id=e3)

    client = LangflowClient(cfg)
    f1, f2, f3 = discover_normdocs_flow_ids(client)
    return replace(cfg, flow_form_id=f1, flow_fill_id=f2, flow_verify_id=f3)
