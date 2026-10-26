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


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> None:
    """ALTER TABLE ... ADD COLUMN unless the column is already present.

    CREATE TABLE IF NOT EXISTS is a no-op once a table exists, so a column
    added after a database is already live has to be migrated in. Existing
    rows take the column default.
    """
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db() -> None:
    """Create schema if not exists. Safe to call on every startup."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id    TEXT    PRIMARY KEY,
                hour_eat   INTEGER NOT NULL DEFAULT 6,
                joined_at  TEXT    NOT NULL,
                source     TEXT    NOT NULL DEFAULT 'command',
                nudges_on  INTEGER NOT NULL DEFAULT 1
            )
        """)
        _add_column_if_missing(
            conn, "subscribers", "nudges_on", "INTEGER NOT NULL DEFAULT 1"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                chat_id        TEXT    NOT NULL,
                activity_date  TEXT    NOT NULL,
                first_seen_at  TEXT    NOT NULL,
                PRIMARY KEY (chat_id, activity_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nudges (
                chat_id     TEXT    NOT NULL,
                nudge_date  TEXT    NOT NULL,
                sent_at     TEXT    NOT NULL,
                PRIMARY KEY (chat_id, nudge_date)
            )
        """)
        conn.commit()
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


def set_nudges(chat_id: str, on: bool) -> bool:
    """Turn nudges on or off for an existing subscriber.

    Returns True if a subscriber row was updated. Daily delivery is
    unaffected: this only gates the reminder.
    """
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE subscribers SET nudges_on = ? WHERE chat_id = ?",
            (1 if on else 0, chat_id),
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
            "SELECT chat_id, hour_eat, joined_at, source, nudges_on"
            " FROM subscribers WHERE chat_id = ?",
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


def record_nudge(chat_id: str, nudge_date: str) -> None:
    """Log that a nudge was sent to chat_id on nudge_date. Idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO nudges (chat_id, nudge_date, sent_at) VALUES (?, ?, ?)",
            (chat_id, nudge_date, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_subscribers_for_nudge(
    *,
    current_hour: int,
    delay_hours: int,
    activity_date: str,
    nudge_date: str,
    active_since: str,
) -> list[dict[str, Any]]:
    """
    Return subscriber rows {chat_id, hour_eat} where:
      (hour_eat + delay_hours) % 24 == current_hour
      AND the subscriber has not turned nudges off
      AND no activity row for activity_date
      AND no nudges row for nudge_date
      AND at least one activity row within [active_since, activity_date]

    That last condition is what ends a run. Someone silent for longer than the
    window is left alone until they come back of their own accord, and a
    subscriber never seen interacting is never nudged at all. The window is
    closed at both ends on purpose: an activity row dated after today, which a
    clock skew or a bad backfill could produce, must not keep someone eligible
    for ever.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT chat_id, hour_eat FROM subscribers
            WHERE (hour_eat + ?) % 24 = ?
              AND nudges_on = 1
              AND chat_id NOT IN (SELECT chat_id FROM activity WHERE activity_date = ?)
              AND chat_id NOT IN (SELECT chat_id FROM nudges WHERE nudge_date = ?)
              AND chat_id IN (
                    SELECT chat_id FROM activity
                    WHERE activity_date >= ? AND activity_date <= ?
              )
            """,
            (
                delay_hours,
                current_hour,
                activity_date,
                nudge_date,
                active_since,
                activity_date,
            ),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
