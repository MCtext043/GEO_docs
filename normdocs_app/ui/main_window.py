from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from normdocs_app.config import AppConfig
from normdocs_app.services.flow_provision import provision_normdocs_flows
from normdocs_app.services.flow_resolve import discover_normdocs_flow_ids
from normdocs_app.services.langflow_client import LangflowClient, LangflowError, humanize_error
from normdocs_app.workers import PipelineMode, run_pipeline_in_thread

SETTINGS_FILE = Path.home() / ".normdocs_langflow_settings.json"

# Палитра: сдержанная «офисная», без ярких акцентов
HEADER_BG = "#1e293b"
HEADER_FG = "#f8fafc"
HEADER_MUTED = "#94a3b8"
BG = "#f1f5f9"
CARD = "#ffffff"
SURFACE = "#f8fafc"
TEXT_MUTED = "#64748b"
TEXT_MAIN = "#0f172a"
ACCENT = "#1e40af"
ACCENT_HOVER = "#1d4ed8"
ACCENT_DIM = "#eff6ff"
BORDER = "#e2e8f0"
BORDER_STRONG = "#cbd5e1"
LOG_BG = "#fafbfc"


def _load_json() -> dict:
    if SETTINGS_FILE.is_file():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_json(data: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _setup_styles(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=BG)
    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(family="Segoe UI", size=10)
    fixed = tkfont.nametofont("TkFixedFont")
    fixed.configure(family="Cascadia Mono", size=9)
    if "Cascadia Mono" not in fixed.actual("family"):
        fixed.configure(family="Consolas", size=9)

    style.configure(".", background=BG, foreground=TEXT_MAIN)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD, relief="flat")
    style.configure("Surface.TFrame", background=SURFACE, relief="flat")
    style.configure("Surface.TLabel", background=SURFACE, foreground=TEXT_MAIN)
    style.configure("TLabel", background=BG, foreground=TEXT_MAIN)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT_MAIN)
    style.configure("Muted.TLabel", background=BG, foreground=TEXT_MUTED, font=("Segoe UI", 9))
    style.configure("Section.TLabel", background=CARD, foreground=TEXT_MAIN, font=("Segoe UI", 10))
    style.configure(
        "TLabelframe",
        background=CARD,
        relief="solid",
        borderwidth=1,
        bordercolor=BORDER,
    )
    style.configure(
        "TLabelframe.Label",
        background=CARD,
        foreground=TEXT_MAIN,
        font=("Segoe UI", 10),
    )
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        padding=(18, 10),
        font=("Segoe UI", 10),
        background=SURFACE,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", CARD), ("!selected", SURFACE)],
        foreground=[("selected", TEXT_MAIN), ("!selected", TEXT_MUTED)],
        expand=[("selected", [1, 1, 1, 0])],
    )
    style.configure("TButton", padding=(12, 7))
    style.map(
        "TButton",
        background=[("active", SURFACE), ("!disabled", CARD)],
        foreground=[("!disabled", TEXT_MAIN)],
    )
    style.configure("Secondary.TButton", padding=(10, 7))
    style.map(
        "Secondary.TButton",
        background=[("active", ACCENT_DIM), ("!disabled", CARD)],
        foreground=[("!disabled", TEXT_MAIN)],
        relief=[("pressed", "sunken"), ("!pressed", "raised")],
    )
    style.configure("Accent.TButton", padding=(14, 9))
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_HOVER), ("!disabled", ACCENT)],
        foreground=[("!disabled", "#ffffff")],
    )
    style.configure("TSpinbox", fieldbackground=CARD, padding=(6, 4), bordercolor=BORDER)
    style.configure("TEntry", fieldbackground=CARD, padding=6, bordercolor=BORDER)
    style.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=ACCENT, thickness=6)
    style.configure("MutedOnCard.TLabel", background=CARD, foreground=TEXT_MUTED, font=("Segoe UI", 9))
    style.configure("TSeparator", background=BORDER)
    return style


def _style_text_widget(w: tk.Text) -> None:
    w.configure(
        selectbackground="#dbeafe",
        selectforeground=TEXT_MAIN,
        insertbackground=ACCENT,
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
        bd=0,
    )


class MainWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("NormDocs — нормативка → отчёт")
        self.root.geometry("1040x840")
        self.root.minsize(900, 660)
        _setup_styles(self.root)

        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._provision_busy = False
        self._check_flows_busy = False

        self._cache_norm_text = ""
        self._cache_data_text = ""
        self._cache_form = ""
        self._cache_filled = ""

        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True)

        header_bar = tk.Frame(outer, bg=HEADER_BG)
        header_bar.pack(fill=tk.X)
        header_inner = tk.Frame(header_bar, bg=HEADER_BG)
        header_inner.pack(fill=tk.X, padx=22, pady=(16, 14))
        tk.Label(
            header_inner,
            text="NormDocs",
            bg=HEADER_BG,
            fg=HEADER_FG,
            font=("Segoe UI", 16),
            anchor=tk.W,
        ).pack(anchor=tk.W)
        tk.Label(
            header_inner,
            text="Нормативные документы и вводные данные → три шага Langflow (по одному или все сразу).",
            bg=HEADER_BG,
            fg=HEADER_MUTED,
            font=("Segoe UI", 9),
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(6, 0))

        body = ttk.Frame(outer, padding=(18, 14))
        body.pack(fill=tk.BOTH, expand=True)

        nb = ttk.Notebook(body)
        nb.pack(fill=tk.BOTH, expand=True)

        # --- Настройки ---
        tab_set = ttk.Frame(nb, padding=(4, 10, 4, 8))
        nb.add(tab_set, text="  Настройки  ")
        card_set = ttk.Frame(tab_set, style="Card.TFrame", padding=(18, 16))
        card_set.pack(fill=tk.BOTH, expand=True)
        f_set = ttk.LabelFrame(card_set, text=" Подключение к Langflow ", padding=(14, 12))
        f_set.pack(fill=tk.X)

        self.var_base = tk.StringVar()
        self.var_key = tk.StringVar()
        self.var_max_norm = tk.IntVar(value=120_000)
        self.var_max_data = tk.IntVar(value=120_000)

        r = 0
        ttk.Label(f_set, text="Базовый URL", style="Card.TLabel").grid(row=r, column=0, sticky=tk.NW, pady=4)
        ttk.Entry(f_set, textvariable=self.var_base, width=58).grid(row=r, column=1, sticky=tk.EW, pady=4, padx=(8, 0))
        r += 1
        ttk.Label(f_set, text="API-ключ", style="Card.TLabel").grid(row=r, column=0, sticky=tk.NW, pady=4)
        ttk.Entry(f_set, textvariable=self.var_key, width=58, show="•").grid(
            row=r, column=1, sticky=tk.EW, pady=4, padx=(8, 0)
        )
        r += 1
        self.var_flow_hint = tk.StringVar(
            value="UUID потоков подставляются с сервера (имена «NormDocs — 1./2./3.»)."
        )
        ttk.Label(f_set, textvariable=self.var_flow_hint, wraplength=720, justify=tk.LEFT, style="MutedOnCard.TLabel").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, pady=(6, 4)
        )
        r += 1
        ttk.Label(f_set, text="Макс. симв. нормативки", style="Card.TLabel").grid(row=r, column=0, sticky=tk.W, pady=4)
        ttk.Spinbox(f_set, from_=5000, to=2_000_000, increment=10000, textvariable=self.var_max_norm, width=14).grid(
            row=r, column=1, sticky=tk.W, pady=4, padx=(8, 0)
        )
        r += 1
        ttk.Label(f_set, text="Макс. симв. вводных", style="Card.TLabel").grid(row=r, column=0, sticky=tk.W, pady=4)
        ttk.Spinbox(f_set, from_=5000, to=2_000_000, increment=10000, textvariable=self.var_max_data, width=14).grid(
            row=r, column=1, sticky=tk.W, pady=4, padx=(8, 0)
        )
        r += 1
        ttk.Button(f_set, text="Сохранить настройки", style="Secondary.TButton", command=self._save_settings).grid(
            row=r, column=1, sticky=tk.W, pady=(12, 4), padx=(8, 0)
        )
        r += 1
        row_btns = ttk.Frame(f_set)
        row_btns.grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
        self.btn_provision = ttk.Button(
            row_btns,
            text="Создать три потока в Langflow",
            style="Secondary.TButton",
            command=self._provision_flows,
        )
        self.btn_provision.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_check_flows = ttk.Button(
            row_btns,
            text="Проверить потоки на сервере",
            style="Secondary.TButton",
            command=self._check_flows_on_server,
        )
        self.btn_check_flows.pack(side=tk.LEFT)
        f_set.columnconfigure(1, weight=1)

        hint = ttk.Label(
            card_set,
            text=(
                "Langflow: URL и ключ (или .env). Потоки создаются кнопкой выше; при работе отчёта UUID ищутся по API. "
                "Документы — только из указанных папок (архив распакуйте вручную)."
            ),
            wraplength=920,
            justify=tk.LEFT,
            style="MutedOnCard.TLabel",
        )
        hint.pack(fill=tk.X, pady=(16, 0))

        # --- Отчёт ---
        tab_run = ttk.Frame(nb, padding=(4, 10, 4, 8))
        nb.add(tab_run, text="  Отчёт  ")
        card_run = ttk.Frame(tab_run, style="Card.TFrame", padding=(18, 16))
        card_run.pack(fill=tk.BOTH, expand=True)

        self.var_norm = tk.StringVar()
        self.var_data = tk.StringVar()

        paths_header = ttk.Label(card_run, text="Источники данных", style="Section.TLabel")
        paths_header.pack(anchor=tk.W, pady=(0, 4))

        def folder_row(parent, label: str, var: tk.StringVar) -> None:
            fr = ttk.Frame(parent, style="Surface.TFrame", padding=(12, 10))
            fr.pack(fill=tk.X, pady=(0, 8))
            ttk.Label(fr, text=label, width=22, style="Surface.TLabel").pack(side=tk.LEFT, anchor=tk.NW)
            ttk.Entry(fr, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
            ttk.Button(fr, text="Обзор…", width=11, style="Secondary.TButton", command=lambda: self._pick_folder(var)).pack(
                side=tk.LEFT
            )

        folder_row(card_run, "Папка с нормативкой", self.var_norm)
        folder_row(card_run, "Папка с вводными", self.var_data)

        ttk.Separator(card_run, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(6, 14))

        steps_fr = ttk.LabelFrame(card_run, text=" Конвейер Langflow ", padding=(14, 12))
        steps_fr.pack(fill=tk.X, pady=(0, 8))

        btn_row = ttk.Frame(steps_fr)
        btn_row.pack(fill=tk.X)
        self.btn_s1 = ttk.Button(
            btn_row,
            text="1 · Форма отчёта",
            style="Secondary.TButton",
            command=lambda: self._start_pipeline("1"),
        )
        self.btn_s1.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_s2 = ttk.Button(
            btn_row,
            text="2 · Заполнение",
            style="Secondary.TButton",
            command=lambda: self._start_pipeline("2"),
        )
        self.btn_s2.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_s3 = ttk.Button(
            btn_row,
            text="3 · Проверка",
            style="Secondary.TButton",
            command=lambda: self._start_pipeline("3"),
        )
        self.btn_s3.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Separator(btn_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)
        self.btn_run = ttk.Button(
            btn_row,
            text="Выполнить все три",
            style="Accent.TButton",
            command=lambda: self._start_pipeline("all"),
        )
        self.btn_run.pack(side=tk.LEFT)

        self.var_status = tk.StringVar(value="Готово к работе.")
        ttk.Label(steps_fr, textvariable=self.var_status, style="MutedOnCard.TLabel").pack(anchor=tk.W, pady=(10, 6))

        self.prog = ttk.Progressbar(steps_fr, mode="indeterminate", style="Horizontal.TProgressbar")
        self.prog.pack(fill=tk.X, pady=(0, 2))

        paned = ttk.PanedWindow(card_run, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        log_frame = ttk.LabelFrame(paned, text=" Журнал ", padding=(8, 6))
        paned.add(log_frame, weight=1)
        self.txt_log = tk.Text(
            log_frame,
            height=9,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg=LOG_BG,
            fg=TEXT_MAIN,
            relief="flat",
            padx=10,
            pady=10,
        )
        _style_text_widget(self.txt_log)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        out_nb = ttk.Notebook(paned)
        paned.add(out_nb, weight=3)

        def make_out_text(parent) -> tk.Text:
            t = tk.Text(
                parent,
                wrap=tk.WORD,
                font=("Segoe UI", 10),
                bg=CARD,
                fg=TEXT_MAIN,
                relief="flat",
                padx=12,
                pady=12,
            )
            _style_text_widget(t)
            return t

        self.txt_form = make_out_text(out_nb)
        self.txt_filled = make_out_text(out_nb)
        self.txt_verify = make_out_text(out_nb)
        out_nb.add(self.txt_form, text="  Шаг 1 · Форма  ")
        out_nb.add(self.txt_filled, text="  Шаг 2 · Заполнение  ")
        out_nb.add(self.txt_verify, text="  Шаг 3 · Проверка  ")

        self._load_settings()
        self._defaults_downloads()
        self._sync_cache_from_widgets()
        self._update_step_buttons()

        self.root.after(200, self._poll_queue)

    def _sync_cache_from_widgets(self) -> None:
        """Подхватить текст из вкладок (если пользователь правил вручную)."""
        self._cache_form = self.txt_form.get("1.0", tk.END).strip()
        self._cache_filled = self.txt_filled.get("1.0", tk.END).strip()

    def _update_step_buttons(self) -> None:
        if self._busy:
            self.btn_s1.configure(state=tk.DISABLED)
            self.btn_s2.configure(state=tk.DISABLED)
            self.btn_s3.configure(state=tk.DISABLED)
            self.btn_run.configure(state=tk.DISABLED)
            return
        self.btn_s1.configure(state=tk.NORMAL)
        self.btn_s2.configure(state=tk.NORMAL if self._cache_form else tk.DISABLED)
        self.btn_s3.configure(state=tk.NORMAL if self._cache_norm_text and self._cache_filled else tk.DISABLED)
        self.btn_run.configure(state=tk.NORMAL)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.prog.start(12)
            self.var_status.set("Выполняется… смотрите журнал ниже.")
        else:
            self.prog.stop()
            self.var_status.set("Готово к работе.")
        self._update_step_buttons()

    def _defaults_downloads(self) -> None:
        dl = Path.home() / "Downloads"
        for name, var in (("нормативка", self.var_norm), ("Пермский край", self.var_data)):
            p = dl / name
            if p.is_dir() and not var.get().strip():
                var.set(str(p.resolve()))

    def _load_settings(self) -> None:
        d = _load_json()
        base = (os.environ.get("LANGFLOW_BASE_URL") or "").strip() or d.get("base_url", "http://127.0.0.1:7860")
        self.var_base.set(str(base).rstrip("/"))
        key = (os.environ.get("LANGFLOW_API_KEY") or "").strip() or d.get("api_key", "")
        self.var_key.set(key)
        self.var_max_norm.set(int(d.get("max_norm", 120_000)))
        self.var_max_data.set(int(d.get("max_data", 120_000)))
        if not self.var_norm.get().strip() and d.get("norm_dir"):
            self.var_norm.set(str(d.get("norm_dir", "")).strip())
        if not self.var_data.get().strip() and d.get("data_dir"):
            self.var_data.set(str(d.get("data_dir", "")).strip())

    def _save_settings(self) -> None:
        api_key_saved = (
            "" if (os.environ.get("LANGFLOW_API_KEY") or "").strip() else self.var_key.get().strip()
        )
        prev = _load_json()
        prev.update(
            {
                "base_url": self.var_base.get().strip(),
                "api_key": api_key_saved,
                "max_norm": self.var_max_norm.get(),
                "max_data": self.var_max_data.get(),
                "norm_dir": self.var_norm.get().strip(),
                "data_dir": self.var_data.get().strip(),
            }
        )
        _save_json(prev)
        messagebox.showinfo("Сохранено", "Настройки записаны в " + str(SETTINGS_FILE))

    def _build_config(self) -> AppConfig:
        d = _load_json()
        return AppConfig(
            langflow_base_url=self.var_base.get().strip() or "http://127.0.0.1:7860",
            api_key=self.var_key.get().strip(),
            flow_form_id=(d.get("flow_form") or "").strip(),
            flow_fill_id=(d.get("flow_fill") or "").strip(),
            flow_verify_id=(d.get("flow_verify") or "").strip(),
            max_corpus_chars=self.var_max_norm.get(),
            max_data_chars=self.var_max_data.get(),
        )

    def _provision_flows(self) -> None:
        if self._provision_busy:
            return
        base = self.var_base.get().strip() or "http://127.0.0.1:7860"
        key = self.var_key.get().strip()
        if not key:
            messagebox.showwarning("API-ключ", "Укажите API-ключ Langflow (или LANGFLOW_API_KEY в .env).")
            return
        cfg = AppConfig(
            langflow_base_url=base,
            api_key=key,
            flow_form_id="",
            flow_fill_id="",
            flow_verify_id="",
            max_corpus_chars=self.var_max_norm.get(),
            max_data_chars=self.var_max_data.get(),
        )
        self._provision_busy = True
        self.btn_provision.configure(state=tk.DISABLED)

        def task() -> None:
            err: str | None = None
            ids: tuple[str, str, str] | None = None
            try:
                ids = provision_normdocs_flows(cfg)
            except LangflowError as e:
                err = humanize_error(e)
            except OSError as e:
                err = humanize_error(e)

            def finish() -> None:
                self._provision_busy = False
                self.btn_provision.configure(state=tk.NORMAL)
                if err:
                    messagebox.showerror("Создание потоков", err)
                elif ids:
                    self.var_flow_hint.set("На сервере создан новый набор из трёх потоков.")
                    messagebox.showinfo(
                        "Готово",
                        "Три потока созданы в Langflow. При запуске шагов приложение найдёт их по API.",
                    )

            self.root.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _check_flows_on_server(self) -> None:
        if self._check_flows_busy or self._provision_busy:
            return
        base = self.var_base.get().strip() or "http://127.0.0.1:7860"
        key = self.var_key.get().strip()
        if not key:
            messagebox.showwarning("API-ключ", "Укажите API-ключ Langflow (или LANGFLOW_API_KEY в .env).")
            return
        cfg = AppConfig(
            langflow_base_url=base,
            api_key=key,
            flow_form_id="",
            flow_fill_id="",
            flow_verify_id="",
            max_corpus_chars=self.var_max_norm.get(),
            max_data_chars=self.var_max_data.get(),
        )
        self._check_flows_busy = True
        self.btn_check_flows.configure(state=tk.DISABLED)

        def task() -> None:
            err: str | None = None
            triple: tuple[str, str, str] | None = None
            try:
                triple = discover_normdocs_flow_ids(LangflowClient(cfg))
            except LangflowError as e:
                err = humanize_error(e)

            def finish() -> None:
                self._check_flows_busy = False
                self.btn_check_flows.configure(state=tk.NORMAL)
                if err:
                    messagebox.showerror("Потоки", err)
                    self.var_flow_hint.set("Потоки NormDocs на сервере не найдены.")
                elif triple:
                    a, b, c = triple
                    self.var_flow_hint.set(
                        f"Найдены 3 потока: {a[:8]}… / {b[:8]}… / {c[:8]}…"
                    )
                    messagebox.showinfo("Потоки", "На сервере найден полный набор из трёх потоков NormDocs.")

            self.root.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _pick_folder(self, var: tk.StringVar) -> None:
        initial = var.get().strip()
        if initial and Path(initial).is_dir():
            initialdir = initial
        else:
            initialdir = str(Path.home() / "Downloads")
        path = filedialog.askdirectory(initialdir=initialdir, mustexist=True)
        if path:
            var.set(str(Path(path).resolve()))

    def _start_pipeline(self, mode: PipelineMode) -> None:
        if self._busy:
            messagebox.showwarning("Занято", "Дождитесь завершения текущей операции.")
            return
        cfg = self._build_config()
        if not cfg.api_key:
            messagebox.showwarning("API-ключ", "Укажите API-ключ на вкладке «Настройки».")
            return

        self._sync_cache_from_widgets()

        norm = self.var_norm.get().strip()
        data = self.var_data.get().strip()

        if mode in ("all", "1"):
            if not norm or not Path(norm).is_dir():
                messagebox.showwarning("Папка", "Укажите папку с нормативными документами.")
                return
        if mode in ("all", "2"):
            if not data or not Path(data).is_dir():
                messagebox.showwarning("Папка", "Укажите папку с вводными данными.")
                return
        if mode == "2" and not self._cache_form:
            messagebox.showwarning("Шаг 2", "Сначала выполните шаг 1 (форма отчёта).")
            return
        if mode == "3":
            if not self._cache_norm_text:
                messagebox.showwarning("Шаг 3", "Сначала выполните шаг 1 (нужен текст нормативки в памяти).")
                return
            if not self._cache_filled:
                messagebox.showwarning("Шаг 3", "Сначала выполните шаг 2 (нужен заполненный отчёт).")
                return

        if mode == "all":
            for w in (self.txt_form, self.txt_filled, self.txt_verify, self.txt_log):
                w.delete("1.0", tk.END)
            self._cache_norm_text = ""
            self._cache_data_text = ""
            self._cache_form = ""
            self._cache_filled = ""
        else:
            self.txt_log.insert(tk.END, f"\n────────── Шаг {mode} ──────────\n")
            self.txt_log.see(tk.END)

        self._set_busy(True)
        run_pipeline_in_thread(
            cfg,
            norm,
            data,
            self._queue,
            mode=mode,
            cached_form=self._cache_form,
            cached_norm_text=self._cache_norm_text,
            cached_data_text=self._cache_data_text,
            cached_filled=self._cache_filled,
        )

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg[0] == "log":
                    self.txt_log.insert(tk.END, msg[1] + "\n")
                    self.txt_log.see(tk.END)
                elif msg[0] == "step":
                    _, title, text = msg
                    if "Форма" in title and "Заполненный" not in title:
                        self.txt_form.delete("1.0", tk.END)
                        self.txt_form.insert("1.0", text)
                    elif "Заполненный" in title:
                        self.txt_filled.delete("1.0", tk.END)
                        self.txt_filled.insert("1.0", text)
                    elif "Проверка" in title:
                        self.txt_verify.delete("1.0", tk.END)
                        self.txt_verify.insert("1.0", text)
                elif msg[0] == "state":
                    _, key, val = msg
                    if key == "norm_text":
                        self._cache_norm_text = val
                    elif key == "data_text":
                        self._cache_data_text = val
                    elif key == "form":
                        self._cache_form = val
                    elif key == "filled":
                        self._cache_filled = val
                    self._update_step_buttons()
                elif msg[0] == "err":
                    messagebox.showerror("Ошибка", msg[1])
                    self._set_busy(False)
                elif msg[0] == "ok":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_queue)

    def run(self) -> None:
        self.root.mainloop()
