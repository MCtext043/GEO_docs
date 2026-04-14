from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from normdocs_app.ui.main_window import MainWindow


def _env_root() -> Path:
    """Каталог с .env: корень проекта или папка с .exe при сборке PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def main() -> None:
    load_dotenv(_env_root() / ".env")
    app = MainWindow()
    app.run()
    sys.exit(0)


if __name__ == "__main__":
    main()
