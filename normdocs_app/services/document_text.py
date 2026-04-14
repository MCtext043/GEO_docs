from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


class TextExtractError(RuntimeError):
    pass


def _read_txt(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    try:
        import fitz
    except ImportError as e:
        raise TextExtractError("Для PDF установите: pip install pymupdf") from e

    doc = fitz.open(path)
    parts: list[str] = []
    try:
        for i in range(doc.page_count):
            parts.append(doc.load_page(i).get_text("text"))
    finally:
        doc.close()
    return "\n".join(parts)


def _read_docx(path: Path) -> str:
    try:
        import docx
    except ImportError as e:
        raise TextExtractError("Для DOCX установите: pip install python-docx") from e

    document = docx.Document(path)
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def extract_file_text(path: Path) -> str:
    path = path.resolve()
    if not path.is_file():
        return ""
    suf = path.suffix.lower()
    if suf in {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}:
        return _read_txt(path)
    if suf == ".pdf":
        return _read_pdf(path)
    if suf in {".docx"}:
        return _read_docx(path)
    if suf in {".doc"}:
        raise TextExtractError(
            f"Старый .doc не поддерживается ({path.name}). Сохраните как .docx или PDF."
        )
    return ""


def collect_corpus(
    root: Path,
    max_chars: int,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[str, list[str]]:
    """Обходит каталог, собирает текст из поддерживаемых файлов.

    on_progress — короткие строки для журнала (например, какой файл читается сейчас).
    """
    root = root.resolve()
    chunks: list[str] = []
    used: list[str] = []
    total = 0
    scanned_files = 0
    with_text = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("~$"):
            continue
        scanned_files += 1
        rel = str(path.relative_to(root))
        suf = path.suffix.lower()
        if on_progress and scanned_files % 40 == 1:
            on_progress(f"  … просмотрено файлов: {scanned_files}, сейчас: {rel[:72]}")
        if on_progress and suf in {".pdf", ".docx"}:
            on_progress(f"  → чтение ({suf}): {rel[:80]}…")
        try:
            text = extract_file_text(path)
        except TextExtractError:
            used.append(f"[пропуск: не прочитан] {rel}")
            if on_progress:
                on_progress(f"  ⊗ пропуск (ошибка формата): {rel[:72]}")
            continue
        if not text.strip():
            continue
        with_text += 1
        if on_progress and (with_text <= 8 or with_text % 25 == 0):
            on_progress(f"  ✓ в корпус #{with_text}: {rel[:72]} ({len(text)} симв.)")
        block = f"===== ФАЙЛ: {rel} =====\n{text.strip()}\n"
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 500:
                chunks.append(block[:remain] + "\n[... обрезано по лимиту ...]")
                used.append(f"{rel} (обрезан)")
            if on_progress:
                on_progress("  ⚠ достигнут лимит символов, остальные файлы не включены.")
            break
        chunks.append(block)
        used.append(rel)
        total += len(block)
    if on_progress:
        on_progress(f"  Итого: просмотрено файлов {scanned_files}, с извлечённым текстом: {with_text}.")
    return "\n".join(chunks), used
