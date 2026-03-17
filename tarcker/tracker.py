"""
Activity tracker: polls the active window and detects idle time.

Supports:
  - Linux (X11) via xdotool / python-xlib / ewmh
  - Linux (Wayland) via hyprctl / swaymsg / kdotool  (best-effort)
  - macOS via AppKit
  - Windows via win32gui
"""

import logging
import platform
import subprocess
import time
from datetime import datetime
from typing import Optional, Tuple

from tarcker import database
from tarcker.config import load_config

logger = logging.getLogger(__name__)

SYSTEM = platform.system()  # "Linux", "Darwin", "Windows"


# ---------------------------------------------------------------------------
# Low-level: get active window info
# ---------------------------------------------------------------------------

def _get_active_window_linux_x11() -> Tuple[str, str]:
    """Return (app_name, window_title) using xdotool."""
    try:
        wid = subprocess.check_output(
            ["xdotool", "getactivewindow"], stderr=subprocess.DEVNULL
        ).decode().strip()
        title = subprocess.check_output(
            ["xdotool", "getwindowname", wid], stderr=subprocess.DEVNULL
        ).decode().strip()
        pid = subprocess.check_output(
            ["xdotool", "getwindowpid", wid], stderr=subprocess.DEVNULL
        ).decode().strip()
        # Get process name from pid
        app = subprocess.check_output(
            ["ps", "-p", pid, "-o", "comm="], stderr=subprocess.DEVNULL
        ).decode().strip()
        return app, title
    except Exception:
        return "unknown", "unknown"


def _get_active_window_linux_wayland() -> Tuple[str, str]:
    """Best-effort Wayland support (Hyprland / Sway / KDE)."""
    # Try Hyprland
    try:
        import json
        out = subprocess.check_output(
            ["hyprctl", "activewindow", "-j"], stderr=subprocess.DEVNULL
        ).decode()
        data = json.loads(out)
        return data.get("class", "unknown"), data.get("title", "unknown")
    except Exception:
        pass
    # Try Sway/i3
    try:
        import json
        out = subprocess.check_output(
            ["swaymsg", "-t", "get_tree"], stderr=subprocess.DEVNULL
        ).decode()
        tree = json.loads(out)
        node = _sway_focused(tree)
        if node:
            app = node.get("app_id") or node.get("window_properties", {}).get("class", "unknown")
            title = node.get("name", "unknown")
            return app, title
    except Exception:
        pass
    return "unknown", "unknown"


def _sway_focused(node: dict) -> Optional[dict]:
    if node.get("focused"):
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        result = _sway_focused(child)
        if result:
            return result
    return None


def _get_active_window_macos() -> Tuple[str, str]:
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().activeApplication()
        app_name = app.get("NSApplicationName", "unknown")
        # Window title requires Accessibility API; fall back to app name
        return app_name, app_name
    except Exception:
        return "unknown", "unknown"


def _get_active_window_windows() -> Tuple[str, str]:
    try:
        import win32gui
        import win32process
        import psutil
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        return proc.name(), title
    except Exception:
        return "unknown", "unknown"


def get_active_window() -> Tuple[str, str]:
    """Return (app_name, window_title) for the currently focused window."""
    if SYSTEM == "Linux":
        # Check whether we're on Wayland
        wayland = (
            "WAYLAND_DISPLAY" in __import__("os").environ
            or __import__("os").environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        )
        if wayland:
            result = _get_active_window_linux_wayland()
            # Some compositors expose both; fall back to X11 via XWayland
            if result[0] == "unknown":
                result = _get_active_window_linux_x11()
            return result
        return _get_active_window_linux_x11()
    elif SYSTEM == "Darwin":
        return _get_active_window_macos()
    elif SYSTEM == "Windows":
        return _get_active_window_windows()
    return "unknown", "unknown"


# ---------------------------------------------------------------------------
# Idle detection
# ---------------------------------------------------------------------------

def _get_idle_seconds_linux() -> float:
    """Seconds since last user input on X11 (via xprintidle)."""
    try:
        ms = int(
            subprocess.check_output(["xprintidle"], stderr=subprocess.DEVNULL).decode().strip()
        )
        return ms / 1000.0
    except Exception:
        return 0.0


def _get_idle_seconds_macos() -> float:
    try:
        out = subprocess.check_output(
            ["ioreg", "-c", "IOHIDSystem"], stderr=subprocess.DEVNULL
        ).decode()
        for line in out.splitlines():
            if "HIDIdleTime" in line:
                ns = int(line.split("=")[-1].strip())
                return ns / 1_000_000_000.0
    except Exception:
        pass
    return 0.0


def _get_idle_seconds_windows() -> float:
    try:
        import ctypes
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    except Exception:
        return 0.0


def get_idle_seconds() -> float:
    if SYSTEM == "Linux":
        return _get_idle_seconds_linux()
    elif SYSTEM == "Darwin":
        return _get_idle_seconds_macos()
    elif SYSTEM == "Windows":
        return _get_idle_seconds_windows()
    return 0.0


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

def categorize(app_name: str, window_title: str, categories: dict) -> str:
    text = f"{app_name} {window_title}".lower()
    for category, keywords in categories.items():
        for kw in keywords:
            if kw in text:
                return category
    return "other"


# ---------------------------------------------------------------------------
# Main tracking loop
# ---------------------------------------------------------------------------

class ActivityTracker:
    def __init__(self):
        self.config = load_config()
        database.init_db()
        self._current_app: Optional[str] = None
        self._current_title: Optional[str] = None
        self._session_start: Optional[datetime] = None
        self._idle_start: Optional[datetime] = None
        self._is_idle = False

    def _flush_session(self, ended_at: datetime) -> None:
        if self._current_app and self._session_start:
            cat = categorize(
                self._current_app,
                self._current_title or "",
                self.config["categories"],
            )
            database.insert_session(
                self._session_start,
                ended_at,
                self._current_app,
                self._current_title or "",
                cat,
            )
            logger.debug(
                "Session: %s | %s | %.0fs",
                self._current_app,
                cat,
                (ended_at - self._session_start).total_seconds(),
            )

    def _flush_idle(self, ended_at: datetime) -> None:
        if self._idle_start:
            database.insert_idle(self._idle_start, ended_at)
            logger.debug(
                "Idle: %.0fs", (ended_at - self._idle_start).total_seconds()
            )
            self._idle_start = None

    def run(self) -> None:
        from tarcker import live_log
        poll = self.config["poll_interval"]
        idle_threshold = self.config["idle_threshold"]
        logger.info("Tarcker started (poll=%ss, idle_threshold=%ss)", poll, idle_threshold)

        while True:
            now = datetime.now()
            idle_s = get_idle_seconds()

            if idle_s >= idle_threshold:
                # User is idle
                if not self._is_idle:
                    # Just became idle: flush current session, start idle period
                    idle_started = datetime.fromtimestamp(now.timestamp() - idle_s)
                    self._flush_session(idle_started)
                    self._current_app = None
                    self._current_title = None
                    self._session_start = None
                    self._idle_start = idle_started
                    self._is_idle = True
                    live_log.log_idle(started=True)
                    logger.debug("User went idle")
            else:
                # User is active
                if self._is_idle:
                    # Just returned from idle
                    self._flush_idle(now)
                    self._is_idle = False
                    live_log.log_idle(started=False)
                    logger.debug("User returned from idle")

                app, title = get_active_window()
                if app != self._current_app or title != self._current_title:
                    # Window changed: flush old session, start new one
                    if self._current_app:
                        self._flush_session(now)
                    self._current_app = app
                    self._current_title = title
                    self._session_start = now
                    cat = categorize(app, title, self.config["categories"])
                    live_log.log_window(app, title, cat)

            time.sleep(poll)
