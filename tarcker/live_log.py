"""
Live activity log — prints a real-time color feed to the terminal so you can
watch what Tarcker is capturing as it happens.

Each event type has its own color and prefix:
  🪟  Window focus change     (cyan)
  ⌨️  Keylog flush            (green)
  🖼️  Screenshot taken        (yellow)
  🌐  Browser visit           (blue)
  💤  Idle started/ended      (dim)

The feed is written to stdout.  Run  python main.py  and watch the terminal,
or redirect to a file:  python main.py >> ~/tarcker.log 2>&1
"""

import threading
from datetime import datetime
from queue import Empty, Queue
from typing import Optional


# ANSI color codes (work in Windows Terminal, PowerShell 7+, any Linux/macOS terminal)
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"
    RED    = "\033[91m"
    GRAY   = "\033[90m"


# Singleton queue — all modules push events here
_queue: Queue = Queue()


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Push helpers (called from tracker, keylogger, screenshot, browser modules)
# ---------------------------------------------------------------------------

def log_window(app: str, title: str, category: str) -> None:
    _queue.put(("window", app, title, category))


def log_keylog(app: str, text: str, char_count: int) -> None:
    _queue.put(("keylog", app, text, char_count))


def log_screenshot(path: str, app: str) -> None:
    _queue.put(("screenshot", path, app))


def log_browser(browser: str, url: str, title: str) -> None:
    _queue.put(("browser", browser, url, title))


def log_idle(started: bool) -> None:
    _queue.put(("idle", started))


def log_browser_sync(count: int) -> None:
    _queue.put(("browser_sync", count))


# ---------------------------------------------------------------------------
# Renderer thread
# ---------------------------------------------------------------------------

class LiveLogRenderer(threading.Thread):
    """Reads from the event queue and prints formatted lines."""

    def __init__(self, config: dict) -> None:
        super().__init__(daemon=True, name="tarcker-livelog")
        cfg = config.get("live_log", {})
        self._enabled        = cfg.get("enabled", True)
        self._show_keys      = cfg.get("show_keystrokes", True)
        self._show_ss        = cfg.get("show_screenshots", True)
        self._show_browser   = cfg.get("show_browser", True)

    def _render(self, event: tuple) -> Optional[str]:
        kind = event[0]

        if kind == "window":
            _, app, title, category = event
            short_title = title[:55] + "…" if len(title) > 55 else title
            return (
                f"{C.GRAY}{_ts()}{C.RESET} "
                f"{C.CYAN}🪟  {C.BOLD}{app}{C.RESET}"
                f"{C.GRAY}  [{category}]  {short_title}{C.RESET}"
            )

        elif kind == "keylog" and self._show_keys:
            _, app, text, char_count = event
            preview = text.replace("\n", "↵").replace("\t", "→")
            preview = preview[:70] + "…" if len(preview) > 70 else preview
            return (
                f"{C.GRAY}{_ts()}{C.RESET} "
                f"{C.GREEN}⌨️   {app}{C.RESET}"
                f"{C.GRAY}  ({char_count} chars)  {C.RESET}"
                f"{C.GREEN}{preview}{C.RESET}"
            )

        elif kind == "screenshot" and self._show_ss:
            _, path, app = event
            fname = path.split("\\")[-1].split("/")[-1]
            return (
                f"{C.GRAY}{_ts()}{C.RESET} "
                f"{C.YELLOW}🖼️   Screenshot salvo{C.RESET}"
                f"{C.GRAY}  {fname}  [{app}]{C.RESET}"
            )

        elif kind == "browser" and self._show_browser:
            _, browser, url, title = event
            short_url = url[:70] + "…" if len(url) > 70 else url
            return (
                f"{C.GRAY}{_ts()}{C.RESET} "
                f"{C.BLUE}🌐  {browser}{C.RESET}"
                f"{C.GRAY}  {short_url}{C.RESET}"
            )

        elif kind == "browser_sync":
            _, count = event
            if count > 0:
                return (
                    f"{C.GRAY}{_ts()}{C.RESET} "
                    f"{C.BLUE}🌐  +{count} visitas sincronizadas do browser{C.RESET}"
                )

        elif kind == "idle":
            _, started = event
            if started:
                return f"{C.GRAY}{_ts()}  💤  Ocioso...{C.RESET}"
            else:
                return f"{C.GRAY}{_ts()}  ▶️   Voltou da ociosidade{C.RESET}"

        return None

    def run(self) -> None:
        if not self._enabled:
            return

        # Print header
        print(
            f"\n{C.BOLD}{C.MAGENTA}"
            f"{'─' * 70}\n"
            f"  TARCKER — Log ao Vivo   (Ctrl+C para parar)\n"
            f"{'─' * 70}"
            f"{C.RESET}\n"
        )

        while True:
            try:
                event = _queue.get(timeout=2)
                line = self._render(event)
                if line:
                    print(line)
            except Empty:
                pass
            except Exception:
                pass
