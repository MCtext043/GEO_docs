from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Literal

from normdocs_app.config import AppConfig
from normdocs_app.services.document_text import collect_corpus, collect_corpus_from_paths
from normdocs_app.services.flow_resolve import resolve_normdocs_flow_ids
from normdocs_app.services.langflow_client import LangflowClient, LangflowError, humanize_error
from normdocs_app.services.mistral_client import MistralError, complete_prompt, summarize_documents
from normdocs_app.services.payloads import (
    payload_direct_summary,
    payload_fill_template,
    payload_form_from_normatives,
    payload_rag_ingest,
    payload_rag_summary,
    payload_verify,
)

# Сообщения: ("log", str) | ("step", title, text) | ("state", key, str) | ("ok",) | ("err", str)

PipelineMode = Literal["all", "1", "2", "3", "summary"]


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


def _collect_files(
    files: list[str],
    max_chars: int,
    ui_queue: queue.Queue,
    intro: str,
) -> tuple[str, list[str]]:
    ui_queue.put(("log", intro))
    paths = [Path(p).resolve() for p in files if str(p).strip()]
    return collect_corpus_from_paths(paths, max_chars, on_progress=_progress_sink(ui_queue))


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


def _run_generation_with_fallback(
    client: LangflowClient,
    cfg: AppConfig,
    flow_id: str,
    prompt: str,
    ui_queue: queue.Queue,
    *,
    stage_label: str,
) -> str:
    try:
        return client.run_flow(flow_id, prompt)
    except LangflowError:
        if not (cfg.mistral_api_key or "").strip():
            raise
        ui_queue.put(
            (
                "log",
                f"{stage_label}: Langflow flow не смог сгенерировать ответ, переключаюсь на прямой Mistral fallback…",
            )
        )
        return complete_prompt(prompt, cfg.mistral_api_key, timeout_sec=cfg.request_timeout_sec)


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
    cached_summary: str = "",
    norm_files: list[str] | None = None,
    data_files: list[str] | None = None,
) -> None:
    """mode=all — полный цикл; 1/2/3/summary — отдельные шаги."""

    def task() -> None:
        try:
            flow_cfg = cfg
            if mode == "summary":
                nroot = Path(norm_dir).resolve() if norm_dir else None
                droot = Path(data_dir).resolve() if data_dir else None
                selected_norm_files = [x for x in (norm_files or []) if str(x).strip()]
                selected_data_files = [x for x in (data_files or []) if str(x).strip()]
                has_sources = (
                    (nroot and nroot.is_dir())
                    or (droot and droot.is_dir())
                    or bool(selected_norm_files)
                    or bool(selected_data_files)
                )
                if not has_sources:
                    ui_queue.put(("err", "Укажите хотя бы одну папку или выберите файлы для суммаризации."))
                    return

                corpus_parts: list[str] = []
                half = max(20_000, flow_cfg.max_summary_chars // 2)
                if selected_norm_files:
                    norm_text, norm_used = _collect_files(
                        selected_norm_files,
                        half,
                        ui_queue,
                        "RAG: чтение выбранных файлов нормативки…",
                    )
                    ui_queue.put(("log", f"RAG: нормативка, файлов в корпусе: {len(norm_used)}."))
                    if norm_text.strip():
                        corpus_parts.append(norm_text)
                        ui_queue.put(("state", "norm_text", norm_text))
                elif nroot and nroot.is_dir():
                    norm_text, norm_entries = _collect(
                        nroot,
                        half,
                        ui_queue,
                        f"RAG: сбор нормативки из папки «{nroot.name}»…",
                    )
                    ui_queue.put(("log", f"RAG: нормативка, записей в корпусе: {len(norm_entries)}."))
                    if norm_text.strip():
                        corpus_parts.append(norm_text)
                        ui_queue.put(("state", "norm_text", norm_text))

                if selected_data_files:
                    current = sum(len(x) for x in corpus_parts)
                    remaining = max(20_000, flow_cfg.max_summary_chars - current)
                    data_text, data_used = _collect_files(
                        selected_data_files,
                        remaining,
                        ui_queue,
                        "RAG: чтение выбранных файлов вводных…",
                    )
                    ui_queue.put(("log", f"RAG: вводные, файлов в корпусе: {len(data_used)}."))
                    if data_text.strip():
                        corpus_parts.append(data_text)
                        ui_queue.put(("state", "data_text", data_text))
                elif droot and droot.is_dir():
                    current = sum(len(x) for x in corpus_parts)
                    remaining = max(20_000, flow_cfg.max_summary_chars - current)
                    data_text, data_entries = _collect(
                        droot,
                        remaining,
                        ui_queue,
                        f"RAG: сбор вводных из папки «{droot.name}»…",
                    )
                    ui_queue.put(("log", f"RAG: вводные, записей в корпусе: {len(data_entries)}."))
                    if data_text.strip():
                        corpus_parts.append(data_text)
                        ui_queue.put(("state", "data_text", data_text))

                documents_corpus = "\n\n".join(p.strip() for p in corpus_parts if p.strip())
                if len(documents_corpus.strip()) < 80:
                    ui_queue.put(("err", "Слишком мало текста для RAG-суммаризации."))
                    return

                client = LangflowClient(flow_cfg)
                collection = (flow_cfg.rag_collection_name or "normdocs_documents").strip()
                rag_ingest = (flow_cfg.flow_rag_ingest_id or "").strip()
                rag_summary = (flow_cfg.flow_rag_summary_id or "").strip()
                if rag_ingest and rag_summary:
                    ui_queue.put(("log", f"RAG: загрузка документов в коллекцию «{collection}»…"))
                    _run_generation_with_fallback(
                        client,
                        flow_cfg,
                        rag_ingest,
                        payload_rag_ingest(collection, documents_corpus),
                        ui_queue,
                        stage_label="RAG ingest",
                    )
                    ui_queue.put(("log", "RAG: индексация завершена, запускаю retrieval + summary…"))
                    summary = _run_generation_with_fallback(
                        client,
                        flow_cfg,
                        rag_summary,
                        payload_rag_summary(collection),
                        ui_queue,
                        stage_label="RAG summary",
                    )
                else:
                    fallback = (flow_cfg.legacy_flow_id or "").strip()
                    if not fallback:
                        ui_queue.put(
                            (
                                "err",
                                "Не указан flow для суммаризации. Задайте LANGFLOW_FLOW_RAG_* "
                                "или LANGFLOW_FLOW_ID в настройках/.env.",
                            )
                        )
                        return
                    ui_queue.put(
                        (
                            "log",
                            "RAG flow не задан. Использую fallback LANGFLOW_FLOW_ID для прямой суммаризации.",
                        )
                    )
                    try:
                        summary = client.run_flow(fallback, payload_direct_summary(documents_corpus))
                    except LangflowError:
                        # Pragmatic fallback for local setup: if flow has no model configured,
                        # use direct Mistral call so user still gets summary immediately.
                        if (flow_cfg.mistral_api_key or "").strip():
                            ui_queue.put(
                                (
                                    "log",
                                    "Langflow flow не смог сгенерировать ответ. Переключаюсь на прямой Mistral fallback…",
                                )
                            )
                            summary = summarize_documents(
                                documents_corpus,
                                flow_cfg.mistral_api_key,
                                timeout_sec=flow_cfg.request_timeout_sec,
                            )
                        else:
                            raise
                ui_queue.put(("step", "RAG-суммаризация", summary))
                ui_queue.put(("state", "summary", summary))
                ui_queue.put(("log", "RAG-суммаризация завершена."))
                ui_queue.put(("ok",))
                return

            if mode in ("all", "1"):
                nroot = Path(norm_dir).resolve()
                if not nroot.is_dir():
                    ui_queue.put(("err", f"Укажите существующую папку с нормативкой: {nroot}"))
                    return
                norm_text, norm_entries = _collect(
                    nroot,
                    flow_cfg.max_corpus_chars,
                    ui_queue,
                    f"Сбор текста из папки с нормативкой «{nroot.name}»…",
                )
                ui_queue.put(("log", f"Нормативка: в корпус попало записей о файлах: {len(norm_entries)}."))
                if len(norm_text.strip()) < 50:
                    ui_queue.put(
                        (
                            "err",
                            "Слишком мало текста из папки с нормативкой. Проверьте форматы (PDF/DOCX/TXT) и вложенные каталоги.",
                        )
                    )
                    return
                ui_queue.put(("state", "norm_text", norm_text))

                resolved = _resolve_and_client(flow_cfg, ui_queue)
                if resolved is None:
                    return
                flow_cfg, client = resolved

                ui_queue.put(("log", "Поток 1 (Langflow): составление формы отчёта…"))
                form = _run_generation_with_fallback(
                    client,
                    flow_cfg,
                    flow_cfg.flow_form_id,
                    payload_form_from_normatives(norm_text),
                    ui_queue,
                    stage_label="Шаг 1",
                )
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
                    data_text, data_entries = _collect(
                        droot,
                        flow_cfg.max_data_chars,
                        ui_queue,
                        f"Сбор текста из папки с вводными «{droot.name}»…",
                    )
                    ui_queue.put(("log", f"Вводные: в корпус попало записей о файлах: {len(data_entries)}."))
                    if len(data_text.strip()) < 20:
                        ui_queue.put(("err", "Слишком мало текста из папки с вводными данными."))
                        return
                    ui_queue.put(("state", "data_text", data_text))

                    resolved = _resolve_and_client(flow_cfg, ui_queue)
                    if resolved is None:
                        return
                    flow_cfg, client = resolved
                else:
                    # mode all: already have norm_text, form, client from above — need data corpus
                    droot = Path(data_dir).resolve()
                    if not droot.is_dir():
                        ui_queue.put(("err", f"Укажите существующую папку с вводными: {droot}"))
                        return
                    data_text, data_entries = _collect(
                        droot,
                        flow_cfg.max_data_chars,
                        ui_queue,
                        f"Сбор текста из папки с вводными «{droot.name}»…",
                    )
                    ui_queue.put(("log", f"Вводные: в корпус попало записей о файлах: {len(data_entries)}."))
                    if len(data_text.strip()) < 20:
                        ui_queue.put(("err", "Слишком мало текста из папки с вводными данными."))
                        return
                    ui_queue.put(("state", "data_text", data_text))

                ui_queue.put(("log", "Поток 2 (Langflow): вставка данных в форму…"))
                filled = _run_generation_with_fallback(
                    client,
                    flow_cfg,
                    flow_cfg.flow_fill_id,
                    payload_fill_template(form, data_text),
                    ui_queue,
                    stage_label="Шаг 2",
                )
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
                    resolved = _resolve_and_client(flow_cfg, ui_queue)
                    if resolved is None:
                        return
                    flow_cfg, client = resolved
                    norm_text, filled = nt, fd
                else:
                    # all: norm_text, filled already in scope from above blocks
                    pass

                ui_queue.put(("log", "Поток 3 (Langflow): проверка по нормативке…"))
                verdict = _run_generation_with_fallback(
                    client,
                    flow_cfg,
                    flow_cfg.flow_verify_id,
                    payload_verify(norm_text, filled),
                    ui_queue,
                    stage_label="Шаг 3",
                )
                ui_queue.put(("step", "Проверка (заключение)", verdict))
                ui_queue.put(("log", "Поток 3 завершён. Готово."))

            ui_queue.put(("ok",))
        except (LangflowError, MistralError, OSError, RuntimeError) as e:
            ui_queue.put(("err", humanize_error(e)))

    t = threading.Thread(target=task, daemon=True)
    t.start()
