"""Создание трёх потоков Langflow через POST /api/v1/flows/.

Шаблон графа (Chat Input → модель → Chat Output) берётся из ответа
GET /api/v1/flows/basic_examples/ — это полные потоки из папки Starter.
При наличии файла assets/normdocs_chat_template.json используется он (офлайн).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from normdocs_app.config import AppConfig
from normdocs_app.services.langflow_client import LangflowClient, LangflowError

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "normdocs_chat_template.json"

# Один и тот же граф подходит для всех трёх шагов: весь смысл в тексте input_value из приложения.
_FLOW_TITLES: tuple[tuple[str, str], ...] = (
    ("NormDocs — 1. Форма отчёта", "Вход: инструкция и корпус нормативки из десктоп-приложения."),
    ("NormDocs — 2. Заполнение", "Вход: форма отчёта и вводные данные из десктоп-приложения."),
    ("NormDocs — 3. Проверка", "Вход: нормативка и заполненный отчёт из десктоп-приложения."),
)


def _flow_base_url(cfg: AppConfig) -> str:
    return cfg.langflow_base_url.rstrip("/") + "/"


def _load_bundle_template() -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Возвращает (data_graph, meta) или None, если файла нет / битый JSON."""
    if not TEMPLATE_PATH.is_file():
        return None
    try:
        root = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(root, dict):
        return None
    data = root.get("data")
    if not isinstance(data, dict) or not data.get("nodes"):
        return None
    meta = {
        "icon": root.get("icon"),
        "icon_bg_color": root.get("icon_bg_color"),
        "gradient": root.get("gradient"),
    }
    return data, meta


def _pick_example_flow(examples: list[Any]) -> dict[str, Any]:
    if not examples:
        raise LangflowError(
            "Список шаблонов Langflow пуст (GET …/flows/basic_examples/). "
            "Откройте Langflow в браузере хотя бы раз, чтобы подтянулись starter-проекты, "
            "либо положите файл normdocs_chat_template.json в normdocs_app/assets/ "
            "(экспорт «Basic Prompting» из репозитория Langflow)."
        )
    for f in examples:
        if not isinstance(f, dict):
            continue
        name = (f.get("name") or "").lower()
        if "basic" in name and "prompt" in name:
            return f
    for f in examples:
        if not isinstance(f, dict):
            continue
        inner = f.get("data")
        if isinstance(inner, dict) and inner.get("nodes"):
            return f
    raise LangflowError(
        "В basic_examples нет потока с полем data.nodes. Обновите Langflow или добавьте шаблон в assets."
    )


def _template_from_basic_examples(client: LangflowClient) -> tuple[dict[str, Any], dict[str, Any]]:
    url = urljoin(_flow_base_url(client.cfg), "api/v1/flows/basic_examples/")
    try:
        r = client.session.get(url, timeout=120)
    except requests.RequestException as e:
        raise LangflowError(f"Сеть при запросе basic_examples: {e}") from e
    if r.status_code == 401:
        raise LangflowError(
            "401: неверный API-ключ Langflow при создании потоков (basic_examples)."
        )
    if r.status_code == 404:
        raise LangflowError(
            "404: endpoint basic_examples не найден — слишком старая версия Langflow. Обновите сервер или используйте файл шаблона в assets."
        )
    if not r.ok:
        raise LangflowError(f"basic_examples: HTTP {r.status_code}: {r.text[:2000]}")
    try:
        examples = r.json()
    except json.JSONDecodeError as e:
        raise LangflowError(f"basic_examples: не JSON: {r.text[:500]}") from e
    if not isinstance(examples, list):
        raise LangflowError("basic_examples: ожидался JSON-массив потоков.")
    picked = _pick_example_flow(examples)
    inner = picked.get("data")
    if not isinstance(inner, dict) or not inner.get("nodes"):
        raise LangflowError("Выбранный шаблон не содержит data.nodes.")
    meta = {
        "icon": picked.get("icon"),
        "icon_bg_color": picked.get("icon_bg_color"),
        "gradient": picked.get("gradient"),
    }
    return inner, meta


def _create_flow(
    client: LangflowClient,
    name: str,
    description: str,
    graph_data: dict[str, Any],
    meta: dict[str, Any],
) -> str:
    url = urljoin(_flow_base_url(client.cfg), "api/v1/flows/")
    body: dict[str, Any] = {
        "name": name,
        "description": description,
        "data": graph_data,
        "tags": ["normdocs"],
    }
    if meta.get("icon") is not None:
        body["icon"] = meta["icon"]
    if meta.get("icon_bg_color") is not None:
        body["icon_bg_color"] = meta["icon_bg_color"]
    if meta.get("gradient") is not None:
        body["gradient"] = meta["gradient"]
    try:
        r = client.session.post(url, json=body, timeout=180)
    except requests.RequestException as e:
        raise LangflowError(f"Сеть при POST /flows/: {e}") from e
    if r.status_code == 401:
        raise LangflowError("401 при создании потока — проверьте API-ключ.")
    if not r.ok:
        raise LangflowError(f"Создание потока «{name}»: HTTP {r.status_code}: {r.text[:2000]}")
    try:
        created = r.json()
    except json.JSONDecodeError as e:
        raise LangflowError(f"Ответ создания потока не JSON: {r.text[:500]}") from e
    fid = created.get("id")
    if not fid:
        raise LangflowError(f"В ответе создания потока нет id: {created!r:.500}")
    return str(fid)


def provision_normdocs_flows(cfg: AppConfig) -> tuple[str, str, str]:
    """
    Создаёт три отдельных потока с одинаковым графом (как в шаблоне).
    Возвращает (flow_form_id, flow_fill_id, flow_verify_id).
    """
    if not (cfg.api_key or "").strip():
        raise LangflowError("Нужен API-ключ Langflow.")
    client = LangflowClient(cfg)

    bundled = _load_bundle_template()
    if bundled is not None:
        graph_data, meta = bundled
    else:
        graph_data, meta = _template_from_basic_examples(client)

    # Уникальные имена при повторном нажатии (ограничение user_id + name в БД Langflow).
    suffix = uuid.uuid4().hex[:8]
    ids: list[str] = []
    for title, desc in _FLOW_TITLES:
        unique_name = f"{title} [{suffix}]"
        ids.append(_create_flow(client, unique_name, desc, graph_data, meta))
    return ids[0], ids[1], ids[2]
