"""Tests for db.py — all run against a temp file DB via DB_PATH monkeypatch."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


def test_add_subscriber_new():
    from db import add_subscriber
    assert add_subscriber("111") is True


def test_add_subscriber_duplicate_returns_false():
    from db import add_subscriber
    add_subscriber("111")
    assert add_subscriber("111") is False


def test_add_subscriber_default_hour_is_6():
    from db import add_subscriber, get_subscriber
    add_subscriber("111")
    assert get_subscriber("111")["hour_eat"] == 6


def test_add_subscriber_custom_hour():
    from db import add_subscriber, get_subscriber
    add_subscriber("111", hour_eat=9)
    assert get_subscriber("111")["hour_eat"] == 9


def test_add_subscriber_source_is_command():
    from db import add_subscriber, get_subscriber
    add_subscriber("111")
    assert get_subscriber("111")["source"] == "command"


def test_remove_subscriber_exists():
    from db import add_subscriber, remove_subscriber
    add_subscriber("111")
    assert remove_subscriber("111") is True


def test_remove_subscriber_not_found():
    from db import remove_subscriber
    assert remove_subscriber("999") is False


def test_remove_subscriber_then_gone():
    from db import add_subscriber, remove_subscriber, get_subscriber
    add_subscriber("111")
    remove_subscriber("111")
    assert get_subscriber("111") is None


def test_get_subscribers_for_hour_single_match():
    from db import add_subscriber, get_subscribers_for_hour
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=9)
    assert get_subscribers_for_hour(6) == ["111"]


def test_get_subscribers_for_hour_multiple_matches():
    from db import add_subscriber, get_subscribers_for_hour
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=6)
    assert set(get_subscribers_for_hour(6)) == {"111", "222"}


def test_get_subscribers_for_hour_no_match():
    from db import get_subscribers_for_hour
    assert get_subscribers_for_hour(14) == []


def test_set_delivery_hour_updates_value():
    from db import add_subscriber, set_delivery_hour, get_subscriber
    add_subscriber("111", hour_eat=6)
    assert set_delivery_hour("111", 9) is True
    assert get_subscriber("111")["hour_eat"] == 9


def test_set_delivery_hour_not_found():
    from db import set_delivery_hour
    assert set_delivery_hour("999", 9) is False


def test_get_subscriber_returns_all_fields():
    from db import add_subscriber, get_subscriber
    add_subscriber("111", hour_eat=7)
    sub = get_subscriber("111")
    assert sub["chat_id"] == "111"
    assert sub["hour_eat"] == 7
    assert sub["source"] == "command"
    assert "joined_at" in sub


def test_get_subscriber_not_found():
    from db import get_subscriber
    assert get_subscriber("999") is None


# --- activity tracking & streaks ---

def test_record_activity_twice_same_day_is_idempotent():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-18")
    record_activity("111", "2026-09-18")  # must not raise
    # total_days_active stays 1 — the composite PK collapsed the second insert
    assert get_streak("111", date(2026, 9, 18)) == (1, 1, 1)


def test_get_streak_no_activity_returns_zeros():
    from db import get_streak
    from datetime import date
    assert get_streak("111", date(2026, 9, 18)) == (0, 0, 0)


def test_get_streak_activity_today_only():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-18")
    assert get_streak("111", date(2026, 9, 18)) == (1, 1, 1)


def test_get_streak_consecutive_days_ending_today():
    from db import record_activity, get_streak
    from datetime import date
    for day in ("2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"):
        record_activity("111", day)
    assert get_streak("111", date(2026, 9, 18)) == (5, 5, 5)


def test_get_streak_grace_day_when_last_activity_was_yesterday():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-17")
    current, longest, total = get_streak("111", date(2026, 9, 18))
    assert current == 1
    assert longest == 1
    assert total == 1


def test_get_streak_broken_when_gap_before_yesterday():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-14")
    current, longest, total = get_streak("111", date(2026, 9, 18))
    assert current == 0
    assert longest == 1
    assert total == 1


def test_get_streak_longest_can_exceed_current():
    from db import record_activity, get_streak
    from datetime import date
    # A broken 4-day run, then a fresh 1-day run today
    for day in ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"):
        record_activity("111", day)
    record_activity("111", "2026-09-18")
    current, longest, total = get_streak("111", date(2026, 9, 18))
    assert current == 1
    assert longest == 4
    assert total == 5


def test_get_streak_only_counts_this_chat_id():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-18")
    record_activity("222", "2026-09-18")
    record_activity("222", "2026-09-17")
    assert get_streak("111", date(2026, 9, 18)) == (1, 1, 1)


# --- nudge eligibility ---

# Nudge eligibility. Today is 2026-09-18, a nudge fires at (hour_eat + 8) % 24,
# and only subscribers seen on or after active_since still get one.
NUDGE_TODAY = "2026-09-18"
NUDGE_ACTIVE_SINCE = "2026-09-15"  # today - 3 days


def _due(current_hour=14, active_since=NUDGE_ACTIVE_SINCE):
    from db import get_subscribers_for_nudge
    return get_subscribers_for_nudge(
        current_hour=current_hour,
        delay_hours=8,
        activity_date=NUDGE_TODAY,
        nudge_date=NUDGE_TODAY,
        active_since=active_since,
    )


def test_get_subscribers_for_nudge_matches_hour():
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-17")
    assert [r["chat_id"] for r in _due()] == ["111"]


def test_get_subscribers_for_nudge_wraps_past_midnight():
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=20)
    record_activity("111", "2026-09-17")
    assert [r["chat_id"] for r in _due(current_hour=4)] == ["111"]


def test_get_subscribers_for_nudge_excludes_non_matching_hour():
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-17")
    assert _due(current_hour=9) == []


def test_get_subscribers_for_nudge_excludes_active_subscriber():
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", NUDGE_TODAY)
    assert _due() == []


def test_get_subscribers_for_nudge_excludes_already_nudged():
    from db import add_subscriber, record_activity, record_nudge
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-17")
    record_nudge("111", NUDGE_TODAY)
    assert _due() == []


def test_get_subscribers_for_nudge_returns_hour_eat():
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-17")
    assert _due()[0]["hour_eat"] == 6


# --- the idle window: what stops a nudge run ---

def test_nudge_included_at_the_window_edge():
    """Last seen exactly active_since. This is the final nudge of the run."""
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", NUDGE_ACTIVE_SINCE)
    assert [r["chat_id"] for r in _due()] == ["111"]


def test_nudge_excluded_one_day_past_the_window():
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-14")  # one day before active_since
    assert _due() == []


def test_nudge_excluded_when_never_seen():
    """No activity at all means we have never seen them interact. Leave them be."""
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)
    assert _due() == []


def test_nudge_uses_most_recent_activity_not_oldest():
    """An old row must not keep someone eligible forever."""
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-08-01")
    assert _due() == []
    record_activity("111", "2026-09-16")
    assert [r["chat_id"] for r in _due()] == ["111"]


def test_nudge_ignores_activity_dated_after_today():
    """A future row (clock skew, bad backfill) must not keep someone eligible."""
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-12-25")
    assert _due() == []


def test_nudge_run_is_capped_at_the_window():
    """Silent from 09-16 onward: nudged on 17, 18, 19, then left alone."""
    from datetime import date, timedelta
    from db import add_subscriber, record_activity, get_subscribers_for_nudge

    add_subscriber("111", hour_eat=6)
    last_seen = date(2026, 9, 16)
    record_activity("111", last_seen.isoformat())

    nudged = []
    for offset in range(1, 8):
        day = last_seen + timedelta(days=offset)
        due = get_subscribers_for_nudge(
            current_hour=14,
            delay_hours=8,
            activity_date=day.isoformat(),
            nudge_date=day.isoformat(),
            active_since=(day - timedelta(days=3)).isoformat(),
        )
        if due:
            nudged.append(day.isoformat())

    assert nudged == ["2026-09-17", "2026-09-18", "2026-09-19"]


def test_nudge_resumes_after_the_subscriber_returns():
    from datetime import timedelta
    from db import add_subscriber, record_activity, get_subscribers_for_nudge
    from datetime import date

    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-01")  # long gone

    def due_on(day: date):
        return get_subscribers_for_nudge(
            current_hour=14,
            delay_hours=8,
            activity_date=day.isoformat(),
            nudge_date=day.isoformat(),
            active_since=(day - timedelta(days=3)).isoformat(),
        )

    assert due_on(date(2026, 9, 20)) == []
    record_activity("111", "2026-09-20")  # they come back
    assert [r["chat_id"] for r in due_on(date(2026, 9, 21))] == ["111"]


def test_record_nudge_is_idempotent():
    from db import record_nudge
    record_nudge("111", "2026-09-18")
    record_nudge("111", "2026-09-18")  # must not raise


# --- nudge opt-out ---

def test_nudges_on_by_default():
    from db import add_subscriber, get_subscriber
    add_subscriber("111")
    assert get_subscriber("111")["nudges_on"] == 1


def test_set_nudges_off():
    from db import add_subscriber, get_subscriber, set_nudges
    add_subscriber("111")
    assert set_nudges("111", False) is True
    assert get_subscriber("111")["nudges_on"] == 0


def test_set_nudges_back_on():
    from db import add_subscriber, get_subscriber, set_nudges
    add_subscriber("111")
    set_nudges("111", False)
    set_nudges("111", True)
    assert get_subscriber("111")["nudges_on"] == 1


def test_set_nudges_unknown_subscriber():
    from db import set_nudges
    assert set_nudges("999", False) is False


def test_nudge_excluded_when_opted_out():
    from db import add_subscriber, record_activity, set_nudges
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-17")
    set_nudges("111", False)
    assert _due() == []


def test_nudge_resumes_when_opted_back_in():
    from db import add_subscriber, record_activity, set_nudges
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-17")
    set_nudges("111", False)
    set_nudges("111", True)
    assert [r["chat_id"] for r in _due()] == ["111"]


def test_opting_out_does_not_stop_daily_delivery():
    """The opt-out is for nudges only; the reading still goes out."""
    from db import add_subscriber, set_nudges, get_subscribers_for_hour
    add_subscriber("111", hour_eat=6)
    set_nudges("111", False)
    assert get_subscribers_for_hour(6) == ["111"]


def test_init_db_adds_nudges_on_to_an_existing_table(monkeypatch, tmp_path):
    """Production already has a subscribers table; init_db must migrate it."""
    import sqlite3
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE subscribers (
            chat_id    TEXT    PRIMARY KEY,
            hour_eat   INTEGER NOT NULL DEFAULT 6,
            joined_at  TEXT    NOT NULL,
            source     TEXT    NOT NULL DEFAULT 'command'
        )
    """)
    conn.execute(
        "INSERT INTO subscribers (chat_id, hour_eat, joined_at, source)"
        " VALUES ('old', 6, '2026-08-30T07:10:06+00:00', 'command')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import get_subscriber, init_db
    init_db()

    assert get_subscriber("old")["nudges_on"] == 1


def test_init_db_is_idempotent_after_migration(monkeypatch, tmp_path):
    db_file = tmp_path / "twice.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()
    init_db()  # must not raise
