"""
Browser history reader — polls Chrome, Edge, and Firefox SQLite history files.

Each browser keeps a locked SQLite file while running, so we copy it to a
temp location before reading. Runs as a background thread, syncing every
N seconds (default 60).

Supported browsers (Windows paths):
  Chrome  : %LOCALAPPDATA%/Google/Chrome/User Data/*/History
  Edge    : %LOCALAPPDATA%/Microsoft/Edge/User Data/*/History
  Brave   : %LOCALAPPDATA%/BraveSoftware/Brave-Browser/User Data/*/History
  Opera   : %APPDATA%/Opera Software/Opera Stable/History
  Firefox : %APPDATA%/Mozilla/Firefox/Profiles/*/places.sqlite
  Vivaldi : %LOCALAPPDATA%/Vivaldi/User Data/*/History

macOS paths are also handled.
"""

import logging
import os
import platform
import shutil
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)
SYSTEM = platform.system()

# Chrome epoch starts at 1601-01-01 (Windows FILETIME epoch)
_CHROME_EPOCH_DELTA = 11_644_473_600  # seconds between 1601-01-01 and 1970-01-01


def _chrome_ts_to_datetime(microseconds: int) -> datetime:
    """Convert Chrome/Edge/Brave timestamp (microseconds since 1601-01-01) to datetime."""
    epoch_s = (microseconds / 1_000_000) - _CHROME_EPOCH_DELTA
    try:
        return datetime.fromtimestamp(epoch_s)
    except (OSError, ValueError, OverflowError):
        return datetime.now()


def _firefox_ts_to_datetime(microseconds: int) -> datetime:
    """Convert Firefox timestamp (microseconds since Unix epoch) to datetime."""
    try:
        return datetime.fromtimestamp(microseconds / 1_000_000)
    except (OSError, ValueError, OverflowError):
        return datetime.now()


# ---------------------------------------------------------------------------
# Profile discovery
# ---------------------------------------------------------------------------

def _local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def _roaming_app_data() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))


def _chromium_profiles(base: Path) -> List[Path]:
    """Return all History files under a Chromium User Data directory."""
    results = []
    if not base.exists():
        return results
    # Default profile
    for profile_name in ["Default", "Profile 1", "Profile 2", "Profile 3",
                         "Profile 4", "Profile 5"]:
        h = base / profile_name / "History"
        if h.exists():
            results.append(h)
    return results


def _discover_browsers() -> List[dict]:
    """Return list of {browser, path, type} dicts."""
    browsers = []

    if SYSTEM == "Windows":
        local = _local_app_data()
        roaming = _roaming_app_data()
        chromium_bases = [
            ("chrome",  local / "Google" / "Chrome" / "User Data"),
            ("edge",    local / "Microsoft" / "Edge" / "User Data"),
            ("brave",   local / "BraveSoftware" / "Brave-Browser" / "User Data"),
            ("vivaldi", local / "Vivaldi" / "User Data"),
            ("opera",   roaming / "Opera Software" / "Opera Stable"),
        ]
        for name, base in chromium_bases:
            for path in _chromium_profiles(base):
                browsers.append({"browser": name, "path": path, "type": "chromium"})

        # Firefox
        ff_profiles = roaming / "Mozilla" / "Firefox" / "Profiles"
        if ff_profiles.exists():
            for profile in ff_profiles.iterdir():
                db = profile / "places.sqlite"
                if db.exists():
                    browsers.append({"browser": "firefox", "path": db, "type": "firefox"})

    elif SYSTEM == "Darwin":
        home = Path.home()
        chromium_bases = [
            ("chrome",  home / "Library/Application Support/Google/Chrome"),
            ("edge",    home / "Library/Application Support/Microsoft Edge"),
            ("brave",   home / "Library/Application Support/BraveSoftware/Brave-Browser"),
            ("vivaldi", home / "Library/Application Support/Vivaldi"),
        ]
        for name, base in chromium_bases:
            for path in _chromium_profiles(base):
                browsers.append({"browser": name, "path": path, "type": "chromium"})

        ff_profiles = home / "Library/Application Support/Firefox/Profiles"
        if ff_profiles.exists():
            for profile in ff_profiles.iterdir():
                db = profile / "places.sqlite"
                if db.exists():
                    browsers.append({"browser": "firefox", "path": db, "type": "firefox"})

    return browsers


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _read_chromium(path: Path, browser: str, since_ts: float) -> List[dict]:
    """Read visits from a Chromium History file since `since_ts` (unix timestamp)."""
    rows = []
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        shutil.copy2(str(path), tmp_path)
        since_chrome = int((since_ts + _CHROME_EPOCH_DELTA) * 1_000_000)
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        try:
            results = conn.execute(
                """
                SELECT u.url, u.title, v.visit_time, u.visit_count
                FROM visits v
                JOIN urls u ON u.id = v.url
                WHERE v.visit_time > ?
                ORDER BY v.visit_time
                """,
                (since_chrome,),
            ).fetchall()
            for r in results:
                ts = _chrome_ts_to_datetime(r["visit_time"])
                rows.append({
                    "timestamp": ts.isoformat(),
                    "browser":   browser,
                    "url":       r["url"],
                    "title":     r["title"] or "",
                    "visit_count": r["visit_count"],
                })
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("Chromium history read error (%s): %s", browser, exc)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return rows


def _read_firefox(path: Path, since_ts: float) -> List[dict]:
    """Read visits from a Firefox places.sqlite file since `since_ts` (unix timestamp)."""
    rows = []
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        shutil.copy2(str(path), tmp_path)
        since_ff = int(since_ts * 1_000_000)
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        try:
            results = conn.execute(
                """
                SELECT p.url, p.title, h.visit_date, p.visit_count
                FROM moz_historyvisits h
                JOIN moz_places p ON p.id = h.place_id
                WHERE h.visit_date > ?
                ORDER BY h.visit_date
                """,
                (since_ff,),
            ).fetchall()
            for r in results:
                ts = _firefox_ts_to_datetime(r["visit_date"])
                rows.append({
                    "timestamp":   ts.isoformat(),
                    "browser":     "firefox",
                    "url":         r["url"],
                    "title":       r["title"] or "",
                    "visit_count": r["visit_count"],
                })
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("Firefox history read error: %s", exc)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return rows


# ---------------------------------------------------------------------------
# Background sync thread
# ---------------------------------------------------------------------------

class BrowserHistorySync(threading.Thread):
    """Polls browser history files every N seconds and stores new visits."""

    def __init__(self, config: dict) -> None:
        super().__init__(daemon=True, name="tarcker-browser-history")
        self._interval = int(config.get("browser_history", {}).get("interval_s", 60))
        self._since_ts: float = time.time() - 86_400  # start from 24h ago on first run

    def _sync(self) -> int:
        from tarcker import database

        browsers = _discover_browsers()
        if not browsers:
            logger.debug("No browser history files found")
            return 0

        all_rows = []
        for b in browsers:
            if b["type"] == "chromium":
                rows = _read_chromium(b["path"], b["browser"], self._since_ts)
            else:
                rows = _read_firefox(b["path"], self._since_ts)
            all_rows.extend(rows)

        inserted = 0
        if all_rows:
            inserted = database.insert_browser_visits(all_rows)
            logger.debug("Browser history: +%d new visits from %d browsers",
                         inserted, len(browsers))
            if inserted > 0:
                from tarcker import live_log
                live_log.log_browser_sync(inserted)
                # Also emit individual recent visits to the feed (last 5)
                for r in all_rows[-5:]:
                    live_log.log_browser(r["browser"], r["url"], r.get("title", ""))
        return inserted

    def run(self) -> None:
        logger.info("Browser history sync started (every %ds)", self._interval)
        while True:
            try:
                self._sync()
                self._since_ts = time.time() - 5  # small overlap to avoid gaps
            except Exception as exc:
                logger.warning("Browser sync error: %s", exc)
            time.sleep(self._interval)
