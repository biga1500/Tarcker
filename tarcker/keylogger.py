"""
Keylogger module — captures keystrokes grouped by active window.

Uses pynput (cross-platform). Stores reconstructed text per typing burst,
NOT raw scancodes, so it's readable for summaries.

Privacy note: password fields are NOT excluded automatically — this is
intentional since the user wants full self-monitoring. Use the
`mask_passwords` config option to redact text typed in known password
managers / lock-screen prompts.
"""

import logging
import re
import threading
import time
from datetime import datetime
from typing import Optional

from pynput import keyboard

from tarcker import database
from tarcker.config import load_config
from tarcker.tracker import get_active_window

logger = logging.getLogger(__name__)

# Special key → printable representation
SPECIAL_KEYS = {
    keyboard.Key.space:     " ",
    keyboard.Key.enter:     "\n",
    keyboard.Key.tab:       "\t",
    keyboard.Key.backspace: "⌫",
    keyboard.Key.delete:    "⌦",
    keyboard.Key.left:      "←",
    keyboard.Key.right:     "→",
    keyboard.Key.up:        "↑",
    keyboard.Key.down:      "↓",
    keyboard.Key.home:      "[Home]",
    keyboard.Key.end:       "[End]",
    keyboard.Key.page_up:   "[PgUp]",
    keyboard.Key.page_down: "[PgDn]",
    keyboard.Key.caps_lock: "[CapsLock]",
    keyboard.Key.esc:       "[Esc]",
    keyboard.Key.f1:        "[F1]",  keyboard.Key.f2:  "[F2]",
    keyboard.Key.f3:        "[F3]",  keyboard.Key.f4:  "[F4]",
    keyboard.Key.f5:        "[F5]",  keyboard.Key.f6:  "[F6]",
    keyboard.Key.f7:        "[F7]",  keyboard.Key.f8:  "[F8]",
    keyboard.Key.f9:        "[F9]",  keyboard.Key.f10: "[F10]",
    keyboard.Key.f11:       "[F11]", keyboard.Key.f12: "[F12]",
}

# Window titles that suggest a password prompt — text is masked
PASSWORD_TITLE_PATTERNS = [
    re.compile(r, re.IGNORECASE)
    for r in [
        r"password", r"senha", r"passphrase", r"unlock",
        r"1password", r"bitwarden", r"keepass", r"lastpass",
        r"credential", r"pin entry",
    ]
]


def _is_password_window(title: str) -> bool:
    return any(p.search(title) for p in PASSWORD_TITLE_PATTERNS)


class KeyLogger(threading.Thread):
    """
    Background thread that listens to keyboard events via pynput and
    batches them into text bursts, flushing to the DB when the window
    changes or after an inactivity gap.
    """

    FLUSH_IDLE_S = 5.0   # flush current buffer after 5 s of no typing

    def __init__(self) -> None:
        super().__init__(daemon=True, name="tarcker-keylogger")
        self._config = load_config()
        self._buf: list[str] = []
        self._buf_app: str = ""
        self._buf_title: str = ""
        self._buf_start: Optional[datetime] = None
        self._last_key_time: float = 0.0
        self._lock = threading.Lock()
        self._ctrl_held = False
        self._alt_held = False

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        with self._lock:
            if not self._buf or not self._buf_start:
                return
            text = "".join(self._buf)
            if text.strip():
                if _is_password_window(self._buf_title):
                    text = "***"  # mask
                database.insert_keylog(
                    self._buf_start,
                    self._buf_app,
                    self._buf_title,
                    text,
                )
                from tarcker import live_log
                live_log.log_keylog(self._buf_app, text, len(text))
                logger.debug(
                    "Keylog flush: %s chars in '%s'", len(text), self._buf_app
                )
            self._buf.clear()
            self._buf_start = None

    def _append(self, char: str) -> None:
        with self._lock:
            now = datetime.now()
            app, title = get_active_window()

            # If window changed, flush current buffer first
            if (app != self._buf_app or title != self._buf_title) and self._buf:
                self._flush()

            if self._buf_start is None:
                self._buf_start = now

            self._buf_app = app
            self._buf_title = title
            self._buf.append(char)
            self._last_key_time = time.monotonic()

    # ------------------------------------------------------------------
    # pynput callbacks
    # ------------------------------------------------------------------

    def _on_press(self, key) -> None:
        try:
            # Track modifier state for Ctrl+C / Ctrl+V etc.
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self._ctrl_held = True
                return
            if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
                       keyboard.Key.alt_gr):
                self._alt_held = True
                return

            # Skip pure modifier combos (Ctrl+S, Alt+Tab, etc.) except
            # Ctrl+V which produces visible pasted text — mark it
            if self._ctrl_held:
                if hasattr(key, "char") and key.char in ("v", "V"):
                    self._append("[Ctrl+V]")
                elif hasattr(key, "char") and key.char in ("c", "C"):
                    self._append("[Ctrl+C]")
                return
            if self._alt_held:
                return

            if hasattr(key, "char") and key.char is not None:
                self._append(key.char)
            elif key in SPECIAL_KEYS:
                self._append(SPECIAL_KEYS[key])

        except Exception as exc:
            logger.debug("Keylogger press error: %s", exc)

    def _on_release(self, key) -> None:
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._ctrl_held = False
        if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
                   keyboard.Key.alt_gr):
            self._alt_held = False

    # ------------------------------------------------------------------
    # Idle-flush loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        logger.info("Keylogger started")
        listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        listener.start()

        while listener.is_alive():
            time.sleep(1)
            if (
                self._last_key_time
                and (time.monotonic() - self._last_key_time) >= self.FLUSH_IDLE_S
                and self._buf
            ):
                self._flush()

        logger.warning("pynput keyboard listener stopped unexpectedly")
