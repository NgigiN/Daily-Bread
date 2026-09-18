"""Tests for subscribe/unsubscribe/settime command handlers."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


# --- /subscribe ---

def test_subscribe_new_default_hour():
    from commands import handle_subscribe
    msgs = handle_subscribe("", chat_id="42")
    assert len(msgs) == 1
    assert "6:00 EAT" in msgs[0]
    assert "✅" in msgs[0]


def test_subscribe_custom_hour():
    from commands import handle_subscribe
    msgs = handle_subscribe("9", chat_id="42")
    assert "9:00 EAT" in msgs[0]
    assert "✅" in msgs[0]


def test_subscribe_hour_zero():
    from commands import handle_subscribe
    msgs = handle_subscribe("0", chat_id="42")
    assert "0:00 EAT" in msgs[0]


def test_subscribe_hour_23():
    from commands import handle_subscribe
    msgs = handle_subscribe("23", chat_id="42")
    assert "23:00 EAT" in msgs[0]


def test_subscribe_already_subscribed():
    from commands import handle_subscribe
    handle_subscribe("", chat_id="42")
    msgs = handle_subscribe("", chat_id="42")
    assert "already subscribed" in msgs[0].lower()
    assert "6:00 EAT" in msgs[0]


def test_subscribe_invalid_hour_too_high():
    from commands import handle_subscribe
    msgs = handle_subscribe("25", chat_id="42")
    assert "0" in msgs[0] and "23" in msgs[0]


def test_subscribe_invalid_hour_negative():
    from commands import handle_subscribe
    msgs = handle_subscribe("-1", chat_id="42")
    assert "0" in msgs[0] and "23" in msgs[0]


def test_subscribe_non_numeric_hour():
    from commands import handle_subscribe
    msgs = handle_subscribe("morning", chat_id="42")
    assert len(msgs) == 1
    assert "number" in msgs[0].lower() or "morning" in msgs[0].lower()


# --- /unsubscribe ---

def test_unsubscribe_existing():
    from commands import handle_subscribe, handle_unsubscribe
    handle_subscribe("", chat_id="42")
    msgs = handle_unsubscribe("", chat_id="42")
    assert "unsubscribed" in msgs[0].lower()


def test_unsubscribe_not_subscribed():
    from commands import handle_unsubscribe
    msgs = handle_unsubscribe("", chat_id="42")
    assert "not subscribed" in msgs[0].lower() or "weren't subscribed" in msgs[0].lower()


def test_unsubscribe_removes_from_db():
    from commands import handle_subscribe, handle_unsubscribe
    from db import get_subscriber
    handle_subscribe("", chat_id="42")
    handle_unsubscribe("", chat_id="42")
    assert get_subscriber("42") is None


# --- /settime ---

def test_settime_updates_hour():
    from commands import handle_subscribe, handle_settime
    from db import get_subscriber
    handle_subscribe("", chat_id="42")
    handle_settime("9", chat_id="42")
    assert get_subscriber("42")["hour_eat"] == 9


def test_settime_reply_confirms_new_hour():
    from commands import handle_subscribe, handle_settime
    handle_subscribe("", chat_id="42")
    msgs = handle_settime("9", chat_id="42")
    assert "9:00 EAT" in msgs[0]
    assert "✅" in msgs[0]


def test_settime_not_subscribed():
    from commands import handle_settime
    msgs = handle_settime("9", chat_id="42")
    assert "not subscribed" in msgs[0].lower()


def test_settime_missing_hour():
    from commands import handle_subscribe, handle_settime
    handle_subscribe("", chat_id="42")
    msgs = handle_settime("", chat_id="42")
    assert "hour" in msgs[0].lower() or "provide" in msgs[0].lower()


def test_settime_invalid_hour():
    from commands import handle_subscribe, handle_settime
    handle_subscribe("", chat_id="42")
    msgs = handle_settime("99", chat_id="42")
    assert "0" in msgs[0] and "23" in msgs[0]


# --- signature compatibility (existing handlers must accept chat_id) ---

def test_handle_help_accepts_chat_id():
    from commands import handle_help
    result = handle_help("", chat_id="99")
    assert isinstance(result, list)
    assert len(result) > 0


def test_handle_start_accepts_chat_id():
    from commands import handle_start
    result = handle_start("", chat_id="99")
    assert isinstance(result, list)


def test_handle_message_text_routes_subscribe():
    from commands import handle_message_text
    msgs = handle_message_text("/subscribe", chat_id="42")
    assert msgs is not None
    assert "✅" in msgs[0] or "subscribed" in msgs[0].lower()


def test_handle_message_text_routes_unsubscribe():
    from commands import handle_message_text
    handle_message_text("/subscribe", chat_id="42")
    msgs = handle_message_text("/unsubscribe", chat_id="42")
    assert msgs is not None
    assert "unsubscribed" in msgs[0].lower()


# --- reflection prompt insertion ---

def test_handle_today_includes_reflection_prompt(monkeypatch):
    import commands
    from formatting import FOOTER

    monkeypatch.setattr(commands, "get_reference_for_date", lambda day: (1, "Monday", "Gen 1"))
    monkeypatch.setattr(
        commands, "fetch_bible_text", lambda ref: ("Gen 1", [("1", "In the beginning...")])
    )
    monkeypatch.setattr(commands, "prompt_for_date", lambda day: "Test reflection prompt?")

    from commands import handle_today
    msgs = handle_today("", chat_id="42")

    assert "Test reflection prompt?" in msgs[-2]
    assert msgs[-1] == FOOTER


# --- /streak ---

def test_handle_streak_not_subscribed():
    from commands import handle_streak
    msgs = handle_streak("", chat_id="42")
    assert "not subscribed" in msgs[0].lower()


def test_handle_streak_shows_current_and_longest(monkeypatch):
    from commands import handle_subscribe, handle_streak
    from db import record_activity
    from datetime import date
    import commands

    handle_subscribe("", chat_id="42")
    record_activity("42", "2026-09-17")
    record_activity("42", "2026-09-18")
    monkeypatch.setattr(commands, "get_eat_today", lambda: date(2026, 9, 18))

    msgs = handle_streak("", chat_id="42")
    assert "Current: 2 days" in msgs[0]
    assert "Longest: 2 days" in msgs[0]
    assert "Total days active: 2" in msgs[0]


def test_handle_streak_singular_day_wording(monkeypatch):
    from commands import handle_subscribe, handle_streak
    from db import record_activity
    from datetime import date
    import commands

    handle_subscribe("", chat_id="42")
    record_activity("42", "2026-09-18")
    monkeypatch.setattr(commands, "get_eat_today", lambda: date(2026, 9, 18))

    msgs = handle_streak("", chat_id="42")
    assert "Current: 1 day\n" in msgs[0]


def test_handle_message_text_routes_streak():
    from commands import handle_message_text, handle_subscribe
    handle_subscribe("", chat_id="42")
    msgs = handle_message_text("/streak", chat_id="42")
    assert msgs is not None
    assert "streak" in msgs[0].lower()
