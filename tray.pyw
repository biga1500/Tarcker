"""
tray.pyw — Roda o Tarcker com ícone na bandeja do sistema (Windows).

Execute com: pythonw tray.pyw
(A extensão .pyw evita abrir uma janela de console)

Requer: pip install pystray pillow
"""

import sys
import threading
from datetime import date
from pathlib import Path


def _require(pkg: str, import_name: str | None = None) -> None:
    try:
        __import__(import_name or pkg)
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


_require("pystray")
_require("Pillow", "PIL")

import pystray
from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Tray icon image (simple colored square with "T")
# ---------------------------------------------------------------------------

def _make_icon() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill="#6366f1")
    draw.text((size // 2, size // 2), "T", fill="white", anchor="mm")
    return img


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _show_summary_today(icon, item):
    import subprocess
    subprocess.Popen(
        [sys.executable, "main.py", "--summary"],
        creationflags=0x00000010,  # CREATE_NEW_CONSOLE
    )


def _open_reports(icon, item):
    import os
    reports = Path.home() / ".tarcker" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    os.startfile(str(reports))


def _open_config(icon, item):
    import os
    from tarcker.config import CONFIG_FILE, load_config
    load_config()  # ensure file exists
    os.startfile(str(CONFIG_FILE))


def _quit(icon, item):
    icon.stop()
    # Stop the tracker thread
    import os
    os._exit(0)


# ---------------------------------------------------------------------------
# Start tracker in background thread
# ---------------------------------------------------------------------------

def _start_tracker():
    from tarcker.tracker import ActivityTracker
    from tarcker.scheduler import DailySummaryScheduler
    from tarcker.config import load_config

    config = load_config()
    scheduler = DailySummaryScheduler(config)
    scheduler.start()

    tracker = ActivityTracker()
    tracker.run()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    tracker_thread = threading.Thread(target=_start_tracker, daemon=True, name="tarcker-main")
    tracker_thread.start()

    menu = pystray.Menu(
        pystray.MenuItem("Ver resumo de hoje", _show_summary_today, default=True),
        pystray.MenuItem("Abrir pasta de relatórios", _open_reports),
        pystray.MenuItem("Editar configurações", _open_config),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", _quit),
    )

    icon = pystray.Icon(
        name="Tarcker",
        icon=_make_icon(),
        title="Tarcker — Monitor de Atividades",
        menu=menu,
    )
    icon.run()


if __name__ == "__main__":
    main()
