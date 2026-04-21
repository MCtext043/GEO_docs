from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

import requests

from normdocs_app.config import AppConfig


class LangflowError(RuntimeError):
    pass


def _translate_http_status(status_code: int) -> str:
    if status_code == 400:
        return "Некорректный запрос к Langflow (HTTP 400). Проверьте входные данные и настройки потока."
    if status_code == 401:
        return "Ошибка авторизации в Langflow (HTTP 401). Проверьте API-ключ."
    if status_code == 403:
        return "Доступ запрещен в Langflow (HTTP 403). Ключ не имеет нужных прав или поток недоступен."
    if status_code == 404:
        return "Ресурс Langflow не найден (HTTP 404). Проверьте URL сервера и UUID потока."
    if status_code == 422:
        return "Langflow не смог обработать запрос (HTTP 422). Проверьте структуру данных и схему потока."
    if status_code == 500:
        return "Внутренняя ошибка сервера Langflow (HTTP 500). Проверьте логи Langflow."
    if status_code == 502:
        return "Шлюз Langflow недоступен (HTTP 502). Проверьте состояние сервера."
    if status_code == 503:
        return "Сервис Langflow временно недоступен (HTTP 503). Повторите попытку позже."
    if status_code == 504:
        return "Langflow не ответил вовремя (HTTP 504). Проверьте нагрузку и таймауты."
    return f"Ошибка HTTP {status_code} при обращении к Langflow."


def _translate_text_message(message: str) -> str:
    msg = (message or "").strip()
    if not msg:
        return "Произошла ошибка при работе с Langflow."

    low = msg.lower()
    if "timed out" in low or "timeout" in low:
        return "Превышено время ожидания ответа от Langflow. Проверьте, что сервер запущен и отвечает."
    if "failed to establish a new connection" in low or "connection refused" in low:
        return "Не удалось подключиться к Langflow. Проверьте URL и что сервер действительно запущен."
    if "name or service not known" in low or "nodename nor servname provided" in low:
        return "Не удалось определить адрес сервера Langflow. Проверьте правильность URL."
    if "ssl" in low and "error" in low:
        return "Ошибка SSL при подключении к Langflow. Проверьте сертификаты или используйте корректный URL."
    if "401 unauthorized" in low:
        return "Ошибка авторизации (401). Проверьте API-ключ Langflow."
    if "404" in low and "not found" in low:
        return "Ресурс не найден в Langflow. Проверьте UUID потока и endpoint."
    if "mistral api http 503" in low or "unreachable_backend" in low:
        return (
            "Сервис модели Mistral временно недоступен (HTTP 503). "
            "Это внешний сбой провайдера, попробуйте повторить запуск через 1-2 минуты."
        )
    if "mistral api http 429" in low or "rate limit" in low:
        return "Превышен лимит запросов к Mistral (429). Подождите немного и повторите запуск."
    if "invalid argument" in low and "errno 22" in low:
        return (
            "Система получила недопустимый путь к файлу. "
            "Проверьте, что выбранные файлы существуют и доступны для чтения."
        )
    if "outdated components" in low and "flow contains" in low:
        return (
            "В Langflow используется устаревший flow-компонент. "
            "Откройте flow и обновите предложенные компоненты, затем запустите снова."
        )

    m = re.search(r"\bHTTP\s+(\d{3})\b", msg, flags=re.IGNORECASE)
    if m:
        return _translate_http_status(int(m.group(1))) + f"\n\nТехнические детали: {msg}"
    return msg


def humanize_error(err: BaseException) -> str:
    if isinstance(err, LangflowError):
        return _translate_text_message(str(err))
    if isinstance(err, requests.Timeout):
        return "Превышено время ожидания ответа от Langflow. Проверьте сеть и доступность сервера."
    if isinstance(err, requests.ConnectionError):
        return "Не удалось подключиться к Langflow. Проверьте URL, сеть и что сервер запущен."
    if isinstance(err, requests.RequestException):
        return _translate_text_message(f"Ошибка сетевого запроса: {err}")
    if isinstance(err, OSError):
        return f"Ошибка доступа к файлам или системе: {err}"
    return _translate_text_message(str(err))


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
