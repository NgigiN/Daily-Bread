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


def test_seed_from_env_populates_empty_db():
    from db import seed_from_env, get_subscribers_for_hour
    count = seed_from_env(["111", "222"], default_hour=5)
    assert count == 2
    assert set(get_subscribers_for_hour(5)) == {"111", "222"}


def test_seed_from_env_sets_source_env_seed():
    from db import seed_from_env, get_subscriber
    seed_from_env(["111"])
    assert get_subscriber("111")["source"] == "env_seed"


def test_seed_from_env_skips_when_db_not_empty():
    from db import add_subscriber, seed_from_env, get_subscriber
    add_subscriber("existing")
    count = seed_from_env(["111", "222"])
    assert count == 0
    assert get_subscriber("111") is None


def test_seed_from_env_empty_list():
    from db import seed_from_env
    assert seed_from_env([]) == 0


def test_seed_from_env_skips_blank_strings():
    from db import seed_from_env, get_subscribers_for_hour
    count = seed_from_env(["111", "  ", "222"])
    assert count == 2


# --- activity tracking & streaks ---

def test_record_activity_then_has_activity_true():
    from db import record_activity, has_activity
    record_activity("111", "2026-09-18")
    assert has_activity("111", "2026-09-18") is True


def test_has_activity_false_for_different_date():
    from db import record_activity, has_activity
    record_activity("111", "2026-09-18")
    assert has_activity("111", "2026-09-19") is False


def test_has_activity_false_when_no_rows():
    from db import has_activity
    assert has_activity("999", "2026-09-18") is False


def test_record_activity_twice_same_day_is_idempotent():
    from db import record_activity, has_activity
    record_activity("111", "2026-09-18")
    record_activity("111", "2026-09-18")  # must not raise
    assert has_activity("111", "2026-09-18") is True


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

def test_get_subscribers_for_nudge_matches_hour():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert [r["chat_id"] for r in result] == ["111"]


def test_get_subscribers_for_nudge_wraps_past_midnight():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=20)
    result = get_subscribers_for_nudge(
        current_hour=4, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert [r["chat_id"] for r in result] == ["111"]


def test_get_subscribers_for_nudge_excludes_non_matching_hour():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    result = get_subscribers_for_nudge(
        current_hour=9, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result == []


def test_get_subscribers_for_nudge_excludes_active_subscriber():
    from db import add_subscriber, record_activity, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-18")
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result == []


def test_get_subscribers_for_nudge_excludes_already_nudged():
    from db import add_subscriber, record_nudge, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    record_nudge("111", "2026-09-18")
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result == []


def test_get_subscribers_for_nudge_returns_hour_eat():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result[0]["hour_eat"] == 6


def test_record_nudge_is_idempotent():
    from db import record_nudge
    record_nudge("111", "2026-09-18")
    record_nudge("111", "2026-09-18")  # must not raise
