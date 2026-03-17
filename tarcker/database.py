"""
SQLite database layer for storing activity records.
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
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS activity_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                ended_at    TEXT,
                app_name    TEXT NOT NULL,
                window_title TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'other',
                duration_s  REAL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_started
                ON activity_sessions(started_at);

            CREATE TABLE IF NOT EXISTS idle_periods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                ended_at    TEXT NOT NULL,
                duration_s  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_idle_started
                ON idle_periods(started_at);
        """)


# ---------------------------------------------------------------------------
# Write helpers
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
            """
            INSERT INTO activity_sessions
                (started_at, ended_at, app_name, window_title, category, duration_s)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                started_at.isoformat(),
                ended_at.isoformat(),
                app_name,
                window_title,
                category,
                duration,
            ),
        )


def insert_idle(started_at: datetime, ended_at: datetime) -> None:
    duration = (ended_at - started_at).total_seconds()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO idle_periods (started_at, ended_at, duration_s) VALUES (?,?,?)",
            (started_at.isoformat(), ended_at.isoformat(), duration),
        )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_sessions_for_date(day: date) -> List[sqlite3.Row]:
    start = f"{day.isoformat()}T00:00:00"
    end = f"{day.isoformat()}T23:59:59"
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM activity_sessions
            WHERE started_at BETWEEN ? AND ?
            ORDER BY started_at
            """,
            (start, end),
        ).fetchall()


def get_idle_for_date(day: date) -> List[sqlite3.Row]:
    start = f"{day.isoformat()}T00:00:00"
    end = f"{day.isoformat()}T23:59:59"
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM idle_periods
            WHERE started_at BETWEEN ? AND ?
            ORDER BY started_at
            """,
            (start, end),
        ).fetchall()


def get_app_totals_for_date(day: date) -> List[dict]:
    """Return total seconds per app for a given day, sorted descending."""
    sessions = get_sessions_for_date(day)
    totals: dict = {}
    for s in sessions:
        key = s["app_name"]
        totals[key] = totals.get(key, {"app_name": key, "category": s["category"], "total_s": 0})
        totals[key]["total_s"] += s["duration_s"]
    return sorted(totals.values(), key=lambda x: x["total_s"], reverse=True)


def get_category_totals_for_date(day: date) -> List[dict]:
    """Return total seconds per category for a given day, sorted descending."""
    sessions = get_sessions_for_date(day)
    totals: dict = {}
    for s in sessions:
        key = s["category"]
        totals[key] = totals.get(key, {"category": key, "total_s": 0})
        totals[key]["total_s"] += s["duration_s"]
    return sorted(totals.values(), key=lambda x: x["total_s"], reverse=True)
