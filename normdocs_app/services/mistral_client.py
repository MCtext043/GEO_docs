from __future__ import annotations

import requests


class MistralError(RuntimeError):
    pass


def complete_prompt(
    prompt: str,
    api_key: str,
    *,
    timeout_sec: int = 180,
    model: str = "mistral-small-latest",
    system_prompt: str = "Отвечай на русском языке, структурировано и по задаче.",
) -> str:
    if not api_key.strip():
        raise MistralError("Не указан MISTRAL_API_KEY.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt.strip()},
        ],
        "temperature": 0.2,
        "max_tokens": 1800,
    }
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout_sec,
        )
    except requests.RequestException as e:
        raise MistralError(f"Сеть/таймаут при обращении к Mistral: {e}") from e
    if not r.ok:
        raise MistralError(f"Ошибка Mistral API HTTP {r.status_code}: {r.text[:600]}")
    data = r.json()
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as e:
        raise MistralError(f"Не удалось извлечь текст из ответа Mistral: {data}") from e


def summarize_documents(
    corpus: str,
    api_key: str,
    *,
    timeout_sec: int = 180,
    model: str = "mistral-small-latest",
) -> str:
    return complete_prompt(
        (
            "Суммаризируй корпус документов.\n"
            "Формат:\n"
            "1) Краткое резюме\n"
            "2) Ключевые требования/тезисы\n"
            "3) Риски и пробелы\n"
            "4) Источники (по именам файлов)\n\n"
            f"{corpus.strip()}"
        ),
        api_key,
        timeout_sec=timeout_sec,
        model=model,
        system_prompt=(
            "Ты эксперт по аналитической суммаризации документов. "
            "Отвечай на русском языке, структурировано и конкретно."
        ),
    )
