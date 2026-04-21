from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
import os
from pathlib import Path
import warnings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class TextExtractError(RuntimeError):
    pass


def _read_txt_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_txt(path: Path) -> str:
    return _read_txt_bytes(path.read_bytes())


def _read_pdf_bytes(raw: bytes) -> str:
    try:
        import fitz
    except ImportError as e:
        raise TextExtractError("Для PDF установите: pip install pymupdf") from e

    doc = fitz.open(stream=raw, filetype="pdf")
    parts: list[str] = []
    try:
        for i in range(doc.page_count):
            parts.append(doc.load_page(i).get_text("text"))
    finally:
        doc.close()
    return "\n".join(parts)


def _read_pdf(path: Path) -> str:
    return _read_pdf_bytes(path.read_bytes())


def _read_docx_bytes(raw: bytes) -> str:
    try:
        import docx
    except ImportError as e:
        raise TextExtractError("Для DOCX установите: pip install python-docx") from e

    document = docx.Document(BytesIO(raw))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def _read_docx(path: Path) -> str:
    return _read_docx_bytes(path.read_bytes())


def _resolve_tesseract_cmd() -> str | None:
    env_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if env_cmd and Path(env_cmd).is_file():
        return env_cmd
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _resolve_tessdata_prefix() -> str | None:
    env_prefix = os.environ.get("TESSDATA_PREFIX", "").strip()
    if env_prefix and Path(env_prefix).is_dir():
        return env_prefix
    for candidate in (
        r"C:\Sirius\tessdata",
        str(Path(__file__).resolve().parents[2] / "tessdata"),
        str(Path(__file__).resolve().parents[2] / ".tessdata"),
    ):
        if Path(candidate).is_dir():
            return candidate
    return None


def _read_image_bytes(raw: bytes) -> str:
    try:
        from PIL import Image
    except ImportError as e:
        raise TextExtractError("Для OCR-изображений установите: pip install pillow") from e
    try:
        import pytesseract
    except ImportError as e:
        raise TextExtractError("Для OCR-изображений установите: pip install pytesseract") from e

    tesseract_cmd = _resolve_tesseract_cmd()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    tessdata_prefix = _resolve_tessdata_prefix()
    if tessdata_prefix:
        os.environ["TESSDATA_PREFIX"] = tessdata_prefix

    requested_langs = os.environ.get("NORMDOCS_OCR_LANGS", "rus+eng").strip() or "rus+eng"
    lang_candidates: list[str] = []
    for candidate in (requested_langs, "eng", "eng+osd"):
        if candidate not in lang_candidates:
            lang_candidates.append(candidate)

    last_error: Exception | None = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(raw))
            image.load()
        with image:
            # Очень большие сканы сильно тормозят OCR: уменьшаем до ограничителя пикселей.
            max_pixels = int(os.environ.get("NORMDOCS_OCR_MAX_PIXELS", "20000000"))
            if image.width * image.height > max_pixels:
                ratio = (max_pixels / float(image.width * image.height)) ** 0.5
                new_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            gray = image.convert("L")
            # OCR может падать на неустановленных языках, поэтому есть fallback-кандидаты.
            for langs in lang_candidates:
                try:
                    return pytesseract.image_to_string(gray, lang=langs)
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    continue
    except Exception as e:  # noqa: BLE001
        raise TextExtractError(f"OCR не выполнился: {e}") from e

    raise TextExtractError(f"OCR не выполнился: {last_error}")


def _read_image(path: Path) -> str:
    return _read_image_bytes(path.read_bytes())


def _extract_rar_text(path: Path) -> str:
    try:
        import rarfile
    except ImportError as e:
        raise TextExtractError("Для RAR установите: pip install rarfile") from e

    seven_zip = Path(r"C:\Program Files\7-Zip\7z.exe")
    if seven_zip.is_file():
        rarfile.SEVENZIP_TOOL = str(seven_zip)

    parts: list[str] = []
    try:
        with rarfile.RarFile(path) as rf:
            for info in rf.infolist():
                if info.isdir():
                    continue
                inner = Path(info.filename)
                suf = inner.suffix.lower()
                if suf not in {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".pdf", ".docx", *IMAGE_SUFFIXES}:
                    continue
                raw = rf.read(info)
                try:
                    if suf in {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}:
                        text = _read_txt_bytes(raw)
                    elif suf == ".pdf":
                        text = _read_pdf_bytes(raw)
                    elif suf == ".docx":
                        text = _read_docx_bytes(raw)
                    else:
                        text = _read_image_bytes(raw)
                except TextExtractError:
                    continue
                if text.strip():
                    parts.append(f"===== ФАЙЛ В АРХИВЕ: {path.name}::{info.filename} =====\n{text.strip()}\n")
    except Exception as e:  # noqa: BLE001
        raise TextExtractError(f"Не удалось прочитать RAR-архив {path.name}: {e}") from e
    return "\n".join(parts)


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
    if suf in IMAGE_SUFFIXES:
        return _read_image(path)
    if suf == ".rar":
        return _extract_rar_text(path)
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


def collect_corpus_from_paths(
    paths: list[Path],
    max_chars: int,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[str, list[str]]:
    """Собирает корпус по списку файлов (без обхода каталогов)."""
    chunks: list[str] = []
    used: list[str] = []
    total = 0
    scanned_files = 0
    with_text = 0
    for path in paths:
        p = path.resolve()
        if not p.is_file() or p.name.startswith("~$"):
            continue
        scanned_files += 1
        rel = str(p)
        suf = p.suffix.lower()
        if on_progress and scanned_files % 20 == 1:
            on_progress(f"  … просмотрено файлов: {scanned_files}, сейчас: {Path(rel).name[:72]}")
        if on_progress and suf in {".pdf", ".docx"}:
            on_progress(f"  → чтение ({suf}): {Path(rel).name[:80]}…")
        try:
            text = extract_file_text(p)
        except TextExtractError:
            used.append(f"[пропуск: не прочитан] {rel}")
            if on_progress:
                on_progress(f"  ⊗ пропуск (ошибка формата): {Path(rel).name[:72]}")
            continue
        if not text.strip():
            continue
        with_text += 1
        if on_progress and (with_text <= 8 or with_text % 25 == 0):
            on_progress(f"  ✓ в корпус #{with_text}: {Path(rel).name[:72]} ({len(text)} симв.)")
        block = f"===== ФАЙЛ: {Path(rel).name} =====\n{text.strip()}\n"
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 500:
                chunks.append(block[:remain] + "\n[... обрезано по лимиту ...]")
                used.append(f"{Path(rel).name} (обрезан)")
            if on_progress:
                on_progress("  ⚠ достигнут лимит символов, остальные файлы не включены.")
            break
        chunks.append(block)
        used.append(rel)
        total += len(block)
    if on_progress:
        on_progress(f"  Итого: выбранных файлов {scanned_files}, с извлечённым текстом: {with_text}.")
    return "\n".join(chunks), used
