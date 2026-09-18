"""Tests for nudge_check.py dispatch logic."""

from __future__ import annotations

from datetime import date, datetime

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


FIXED_NOW = datetime(2026, 9, 18, 14, 0, 0)
FIXED_TODAY = date(2026, 9, 18)


def test_main_does_nothing_when_none_due(monkeypatch):
    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    import nudge_check
    nudge_check.main()  # must not raise; no subscribers exist


def test_main_sends_nudge_to_eligible_subscriber(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)  # nudge hour = (6 + 8) % 24 = 14

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )

    import nudge_check
    nudge_check.main()

    assert sent_to == ["111"]


def test_main_does_not_double_nudge_same_day(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )

    import nudge_check
    nudge_check.main()
    nudge_check.main()

    assert sent_to == ["111"]


def test_main_skips_subscriber_with_activity_today(monkeypatch):
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-18")

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )

    import nudge_check
    nudge_check.main()

    assert sent_to == []


def test_main_does_not_record_nudge_on_failed_send(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)
    monkeypatch.setattr(
        "nudge_check.send_messages", lambda chat_id, messages, **kwargs: False
    )

    import nudge_check
    nudge_check.main()

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )
    nudge_check.main()

    assert sent_to == ["111"]
