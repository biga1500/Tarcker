"""
SQLite database layer for storing all activity records.
"""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Generator, List, Optional

DB_PATH = Path.home() / ".tarcker" / "activity.db"


def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(get_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # allow concurrent readers/writers
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            -- Window focus sessions
            CREATE TABLE IF NOT EXISTS activity_sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at   TEXT NOT NULL,
                ended_at     TEXT,
                app_name     TEXT NOT NULL,
                window_title TEXT NOT NULL,
                category     TEXT NOT NULL DEFAULT 'other',
                duration_s   REAL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_started
                ON activity_sessions(started_at);

            -- Idle periods
            CREATE TABLE IF NOT EXISTS idle_periods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                ended_at    TEXT NOT NULL,
                duration_s  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_idle_started
                ON idle_periods(started_at);

            -- Keylog: one row per "burst" of typing in a window
            CREATE TABLE IF NOT EXISTS keylog_entries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT NOT NULL,
                app_name     TEXT NOT NULL,
                window_title TEXT NOT NULL,
                text         TEXT NOT NULL,       -- reconstructed text (no raw passwords*)
                char_count   INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_keylog_ts
                ON keylog_entries(timestamp);

            -- Screenshots metadata
            CREATE TABLE IF NOT EXISTS screenshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                filepath    TEXT NOT NULL,
                app_name    TEXT,
                window_title TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_screenshots_ts
                ON screenshots(timestamp);

            -- Browser visits (from history files)
            CREATE TABLE IF NOT EXISTS browser_visits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                browser     TEXT NOT NULL,
                url         TEXT NOT NULL,
                title       TEXT,
                visit_count INTEGER DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_visits_ts
                ON browser_visits(timestamp);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_visits_unique
                ON browser_visits(browser, url, timestamp);
        """)


# ---------------------------------------------------------------------------
# Window sessions
# ---------------------------------------------------------------------------

def insert_session(
    started_at: datetime,
    ended_at: datetime,
    app_name: str,
    window_title: str,
    category: str,
) -> None:
    duration = (ended_at - started_at).total_seconds()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO activity_sessions
               (started_at, ended_at, app_name, window_title, category, duration_s)
               VALUES (?,?,?,?,?,?)""",
            (started_at.isoformat(), ended_at.isoformat(),
             app_name, window_title, category, duration),
        )


def insert_idle(started_at: datetime, ended_at: datetime) -> None:
    duration = (ended_at - started_at).total_seconds()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO idle_periods (started_at, ended_at, duration_s) VALUES (?,?,?)",
            (started_at.isoformat(), ended_at.isoformat(), duration),
        )


# ---------------------------------------------------------------------------
# Keylog
# ---------------------------------------------------------------------------

def insert_keylog(
    timestamp: datetime,
    app_name: str,
    window_title: str,
    text: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO keylog_entries
               (timestamp, app_name, window_title, text, char_count)
               VALUES (?,?,?,?,?)""",
            (timestamp.isoformat(), app_name, window_title, text, len(text)),
        )


def get_keylog_for_date(day: date) -> List[sqlite3.Row]:
    start = f"{day.isoformat()}T00:00:00"
    end   = f"{day.isoformat()}T23:59:59"
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM keylog_entries WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp",
            (start, end),
        ).fetchall()


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

def insert_screenshot(
    timestamp: datetime,
    filepath: str,
    app_name: str,
    window_title: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO screenshots (timestamp, filepath, app_name, window_title)
               VALUES (?,?,?,?)""",
            (timestamp.isoformat(), filepath, app_name, window_title),
        )


def get_screenshots_for_date(day: date) -> List[sqlite3.Row]:
    start = f"{day.isoformat()}T00:00:00"
    end   = f"{day.isoformat()}T23:59:59"
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM screenshots WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp",
            (start, end),
        ).fetchall()


# ---------------------------------------------------------------------------
# Browser visits
# ---------------------------------------------------------------------------

def insert_browser_visits(rows: List[dict]) -> int:
    """Bulk-insert browser history rows. Returns number of new rows inserted."""
    inserted = 0
    with get_conn() as conn:
        for r in rows:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO browser_visits
                       (timestamp, browser, url, title, visit_count)
                       VALUES (?,?,?,?,?)""",
                    (r["timestamp"], r["browser"], r["url"],
                     r.get("title", ""), r.get("visit_count", 1)),
                )
                inserted += conn.execute("SELECT changes()").fetchone()[0]
            except Exception:
                pass
    return inserted


def get_browser_visits_for_date(day: date) -> List[sqlite3.Row]:
    start = f"{day.isoformat()}T00:00:00"
    end   = f"{day.isoformat()}T23:59:59"
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM browser_visits
               WHERE timestamp BETWEEN ? AND ?
               ORDER BY timestamp""",
            (start, end),
        ).fetchall()


# ---------------------------------------------------------------------------
# Aggregates (used by summarizer)
# ---------------------------------------------------------------------------

def get_sessions_for_date(day: date) -> List[sqlite3.Row]:
    start = f"{day.isoformat()}T00:00:00"
    end   = f"{day.isoformat()}T23:59:59"
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM activity_sessions WHERE started_at BETWEEN ? AND ? ORDER BY started_at",
            (start, end),
        ).fetchall()


def get_idle_for_date(day: date) -> List[sqlite3.Row]:
    start = f"{day.isoformat()}T00:00:00"
    end   = f"{day.isoformat()}T23:59:59"
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM idle_periods WHERE started_at BETWEEN ? AND ? ORDER BY started_at",
            (start, end),
        ).fetchall()


def get_app_totals_for_date(day: date) -> List[dict]:
    sessions = get_sessions_for_date(day)
    totals: dict = {}
    for s in sessions:
        key = s["app_name"]
        totals.setdefault(key, {"app_name": key, "category": s["category"], "total_s": 0.0})
        totals[key]["total_s"] += s["duration_s"]
    return sorted(totals.values(), key=lambda x: x["total_s"], reverse=True)


def get_category_totals_for_date(day: date) -> List[dict]:
    sessions = get_sessions_for_date(day)
    totals: dict = {}
    for s in sessions:
        key = s["category"]
        totals.setdefault(key, {"category": key, "total_s": 0.0})
        totals[key]["total_s"] += s["duration_s"]
    return sorted(totals.values(), key=lambda x: x["total_s"], reverse=True)
