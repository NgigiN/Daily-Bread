"""SQLite subscriber store. One table, stdlib sqlite3 only."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any

from config import get_db_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create schema if not exists. Safe to call on every startup."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id    TEXT    PRIMARY KEY,
                hour_eat   INTEGER NOT NULL DEFAULT 6,
                joined_at  TEXT    NOT NULL,
                source     TEXT    NOT NULL DEFAULT 'command'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                chat_id        TEXT    NOT NULL,
                activity_date  TEXT    NOT NULL,
                first_seen_at  TEXT    NOT NULL,
                PRIMARY KEY (chat_id, activity_date)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def seed_from_env(chat_ids: list[str], *, default_hour: int = 6) -> int:
    """Insert chat_ids into an empty table (source='env_seed'). No-ops if table has rows.

    WARNING: This only seeds when the table is completely empty. If all subscribers
    later unsubscribe, the next restart will re-seed from TELEGRAM_CHAT_IDS.
    To prevent this, remove TELEGRAM_CHAT_IDS from .env after the first deploy
    (see deploy checklist Task 5 Step 7).
    """
    if not chat_ids:
        return 0
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
        if count > 0:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        for chat_id in [c.strip() for c in chat_ids if c.strip()]:
            cur = conn.execute(
                "INSERT OR IGNORE INTO subscribers (chat_id, hour_eat, joined_at, source)"
                " VALUES (?, ?, ?, ?)",
                (chat_id, default_hour, now, "env_seed"),
            )
            inserted += cur.rowcount
        conn.commit()
        return inserted
    finally:
        conn.close()


def add_subscriber(chat_id: str, *, hour_eat: int = 6) -> bool:
    """Insert subscriber. Returns True if newly inserted, False if already existed."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, hour_eat, joined_at, source)"
            " VALUES (?, ?, ?, ?)",
            (chat_id, hour_eat, now, "command"),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def remove_subscriber(chat_id: str) -> bool:
    """Delete subscriber. Returns True if a row was deleted."""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_delivery_hour(chat_id: str, hour_eat: int) -> bool:
    """Update delivery hour for an existing subscriber. Returns True if found and updated."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE subscribers SET hour_eat = ? WHERE chat_id = ?",
            (hour_eat, chat_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_subscribers_for_hour(hour_eat: int) -> list[str]:
    """Return chat_ids whose stored delivery hour matches hour_eat."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT chat_id FROM subscribers WHERE hour_eat = ?", (hour_eat,)
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_subscriber(chat_id: str) -> dict[str, Any] | None:
    """Return subscriber row as dict, or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT chat_id, hour_eat, joined_at, source FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_subscribers() -> int:
    """Return total number of subscribers."""
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def record_activity(chat_id: str, activity_date: str) -> None:
    """Log an interaction for chat_id on activity_date (YYYY-MM-DD). Idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO activity (chat_id, activity_date, first_seen_at)"
            " VALUES (?, ?, ?)",
            (chat_id, activity_date, now),
        )
        conn.commit()
    finally:
        conn.close()


def has_activity(chat_id: str, activity_date: str) -> bool:
    """True if chat_id has an activity row for activity_date."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM activity WHERE chat_id = ? AND activity_date = ?",
            (chat_id, activity_date),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_streak(chat_id: str, today: date) -> tuple[int, int, int]:
    """
    Return (current_streak, longest_streak, total_days_active) for chat_id.

    current_streak is 0 if the most recent activity date isn't today or
    yesterday relative to `today`.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT activity_date FROM activity WHERE chat_id = ? ORDER BY activity_date DESC",
            (chat_id,),
        ).fetchall()
    finally:
        conn.close()

    dates = [date.fromisoformat(row[0]) for row in rows]
    total = len(dates)
    if not dates:
        return 0, 0, 0

    current = 0
    if dates[0] in (today, today - timedelta(days=1)):
        current = 1
        for i in range(1, len(dates)):
            if dates[i - 1] - dates[i] == timedelta(days=1):
                current += 1
            else:
                break

    ascending = sorted(dates)
    longest = run = 1
    for i in range(1, len(ascending)):
        if ascending[i] - ascending[i - 1] == timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return current, longest, total
