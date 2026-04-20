from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Literal

from normdocs_app.config import AppConfig
from normdocs_app.services.document_text import collect_corpus
from normdocs_app.services.flow_resolve import resolve_normdocs_flow_ids
from normdocs_app.services.langflow_client import LangflowClient, LangflowError, humanize_error
from normdocs_app.services.payloads import payload_fill_template, payload_form_from_normatives, payload_verify

# Сообщения: ("log", str) | ("step", title, text) | ("state", key, str) | ("ok",) | ("err", str)

PipelineMode = Literal["all", "1", "2", "3"]


def _progress_sink(ui_queue: queue.Queue):
    return lambda m: ui_queue.put(("log", m))


def _collect(
    root: Path,
    max_chars: int,
    ui_queue: queue.Queue,
    intro: str,
) -> tuple[str, list[str]]:
    ui_queue.put(("log", intro))
    return collect_corpus(root, max_chars, on_progress=_progress_sink(ui_queue))


def _resolve_and_client(cfg: AppConfig, ui_queue: queue.Queue) -> tuple[AppConfig, LangflowClient] | None:
    ui_queue.put(("log", "Поиск потоков NormDocs на сервере Langflow…"))
    try:
        cfg = resolve_normdocs_flow_ids(cfg)
    except LangflowError as e:
        ui_queue.put(("err", humanize_error(e)))
        return None
    ui_queue.put(
        (
            "log",
            f"Потоки: форма={cfg.flow_form_id[:8]}…, данные={cfg.flow_fill_id[:8]}…, проверка={cfg.flow_verify_id[:8]}…",
        )
    )
    return cfg, LangflowClient(cfg)


def run_pipeline_in_thread(
    cfg: AppConfig,
    norm_dir: str,
    data_dir: str,
    ui_queue: queue.Queue,
    *,
    mode: PipelineMode = "all",
    cached_form: str = "",
    cached_norm_text: str = "",
    cached_data_text: str = "",
    cached_filled: str = "",
) -> None:
    """mode=all — полный цикл; 1/2/3 — отдельные шаги (нужны данные из кэша UI)."""

    def task() -> None:
        try:
            if mode in ("all", "1"):
                nroot = Path(norm_dir).resolve()
                if not nroot.is_dir():
                    ui_queue.put(("err", f"Укажите существующую папку с нормативкой: {nroot}"))
                    return
                norm_text, norm_files = _collect(
                    nroot,
                    cfg.max_corpus_chars,
                    ui_queue,
                    f"Сбор текста из папки с нормативкой «{nroot.name}»…",
                )
                ui_queue.put(("log", f"Нормативка: в корпус попало записей о файлах: {len(norm_files)}."))
                if len(norm_text.strip()) < 50:
                    ui_queue.put(
                        (
                            "err",
                            "Слишком мало текста из папки с нормативкой. Проверьте форматы (PDF/DOCX/TXT) и вложенные каталоги.",
                        )
                    )
                    return
                ui_queue.put(("state", "norm_text", norm_text))

                resolved = _resolve_and_client(cfg, ui_queue)
                if resolved is None:
                    return
                cfg, client = resolved

                ui_queue.put(("log", "Поток 1 (Langflow): составление формы отчёта…"))
                form = client.run_flow(cfg.flow_form_id, payload_form_from_normatives(norm_text))
                ui_queue.put(("step", "Форма отчёта", form))
                ui_queue.put(("state", "form", form))
                ui_queue.put(("log", "Поток 1 завершён."))

                if mode == "1":
                    ui_queue.put(("ok",))
                    return

            if mode in ("all", "2"):
                if mode == "2":
                    form = cached_form.strip()
                    if not form:
                        ui_queue.put(("err", "Сначала выполните шаг 1 (форма отчёта)."))
                        return
                    droot = Path(data_dir).resolve()
                    if not droot.is_dir():
                        ui_queue.put(("err", f"Укажите существующую папку с вводными: {droot}"))
                        return
                    data_text, data_files = _collect(
                        droot,
                        cfg.max_data_chars,
                        ui_queue,
                        f"Сбор текста из папки с вводными «{droot.name}»…",
                    )
                    ui_queue.put(("log", f"Вводные: в корпус попало записей о файлах: {len(data_files)}."))
                    if len(data_text.strip()) < 20:
                        ui_queue.put(("err", "Слишком мало текста из папки с вводными данными."))
                        return
                    ui_queue.put(("state", "data_text", data_text))

                    resolved = _resolve_and_client(cfg, ui_queue)
                    if resolved is None:
                        return
                    cfg, client = resolved
                else:
                    # mode all: already have norm_text, form, client from above — need data corpus
                    droot = Path(data_dir).resolve()
                    if not droot.is_dir():
                        ui_queue.put(("err", f"Укажите существующую папку с вводными: {droot}"))
                        return
                    data_text, data_files = _collect(
                        droot,
                        cfg.max_data_chars,
                        ui_queue,
                        f"Сбор текста из папки с вводными «{droot.name}»…",
                    )
                    ui_queue.put(("log", f"Вводные: в корпус попало записей о файлах: {len(data_files)}."))
                    if len(data_text.strip()) < 20:
                        ui_queue.put(("err", "Слишком мало текста из папки с вводными данными."))
                        return
                    ui_queue.put(("state", "data_text", data_text))

                ui_queue.put(("log", "Поток 2 (Langflow): вставка данных в форму…"))
                filled = client.run_flow(cfg.flow_fill_id, payload_fill_template(form, data_text))
                ui_queue.put(("step", "Заполненный отчёт", filled))
                ui_queue.put(("state", "filled", filled))
                ui_queue.put(("log", "Поток 2 завершён."))

                if mode == "2":
                    ui_queue.put(("ok",))
                    return

            if mode in ("all", "3"):
                if mode == "3":
                    nt = cached_norm_text.strip()
                    fd = cached_filled.strip()
                    if not nt:
                        ui_queue.put(("err", "Нет текста нормативки — выполните шаг 1."))
                        return
                    if not fd:
                        ui_queue.put(("err", "Нет заполненного отчёта — выполните шаг 2."))
                        return
                    resolved = _resolve_and_client(cfg, ui_queue)
                    if resolved is None:
                        return
                    cfg, client = resolved
                    norm_text, filled = nt, fd
                else:
                    # all: norm_text, filled already in scope from above blocks
                    pass

                ui_queue.put(("log", "Поток 3 (Langflow): проверка по нормативке…"))
                verdict = client.run_flow(cfg.flow_verify_id, payload_verify(norm_text, filled))
                ui_queue.put(("step", "Проверка (заключение)", verdict))
                ui_queue.put(("log", "Поток 3 завершён. Готово."))

            ui_queue.put(("ok",))
        except (LangflowError, OSError, RuntimeError) as e:
            ui_queue.put(("err", humanize_error(e)))

    t = threading.Thread(target=task, daemon=True)
    t.start()
