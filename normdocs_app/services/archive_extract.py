from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class ArchiveExtractError(RuntimeError):
    pass


def _seven_zip_candidates() -> list[Path]:
    paths: list[Path] = []
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for base in (pf, pfx86):
        paths.append(Path(base) / "7-Zip" / "7z.exe")
    which = shutil.which("7z")
    if which:
        paths.append(Path(which))
    return paths


def extract_archive(archive_path: str | Path, dest_dir: str | Path | None = None) -> Path:
    """Распаковывает .rar или .zip в каталог. Предпочитает 7-Zip на Windows."""
    archive_path = Path(archive_path).resolve()
    if not archive_path.is_file():
        raise ArchiveExtractError(f"Файл не найден: {archive_path}")

    suffix = archive_path.suffix.lower()
    if suffix not in {".rar", ".zip", ".7z"}:
        raise ArchiveExtractError(f"Поддерживаются архивы .rar / .zip / .7z, получено: {suffix}")

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="normdocs_arc_"))
    else:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

    seven = next((p for p in _seven_zip_candidates() if p.is_file()), None)
    if seven:
        r = subprocess.run(
            [str(seven), "x", str(archive_path), f"-o{dest_dir}", "-y"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode != 0:
            raise ArchiveExtractError(
                f"7-Zip завершился с кодом {r.returncode}.\n{r.stderr or r.stdout}"
            )
        return dest_dir

    try:
        import rarfile
    except ImportError as e:
        raise ArchiveExtractError(
            "Не найден 7-Zip (7z.exe) и не установлен пакет rarfile. "
            "Установите 7-Zip с https://www.7-zip.org/ или: pip install rarfile "
            "(для RAR также нужен UnRAR)."
        ) from e

    if suffix == ".rar":
        rf = rarfile.RarFile(archive_path)
        rf.extractall(dest_dir)
        return dest_dir

    import zipfile

    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(dest_dir)
    return dest_dir
