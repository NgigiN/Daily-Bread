"""Tests for daily_bread.py dispatch logic."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


def test_get_recipients_returns_matching_hour(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=9)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    from daily_bread import _get_recipients
    assert _get_recipients() == ["111"]


def test_get_recipients_empty_when_no_match(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 14)

    from daily_bread import _get_recipients
    assert _get_recipients() == []


def test_get_recipients_multiple_at_same_hour(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=8)
    add_subscriber("222", hour_eat=8)
    add_subscriber("333", hour_eat=9)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 8)

    from daily_bread import _get_recipients
    assert set(_get_recipients()) == {"111", "222"}


def test_main_exits_early_when_no_subscribers(monkeypatch, capsys):
    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 3)

    import daily_bread
    daily_bread.main()

    captured = capsys.readouterr()
    assert "dispatch_no_subscribers" in captured.out
    assert '"hour":3' in captured.out


def test_main_sends_to_matching_subscribers(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    sent_to = []

    def mock_send(chat_id, messages, **kwargs):
        sent_to.append(str(chat_id))
        return True

    monkeypatch.setattr("daily_bread.send_messages", mock_send)
    monkeypatch.setattr(
        "daily_bread.get_reference_for_today",
        lambda today: (1, "Monday", "Gen 1"),
    )
    monkeypatch.setattr(
        "daily_bread.fetch_bible_text",
        lambda ref: ("Gen 1", [("1", "In the beginning God created...")]),
    )
    monkeypatch.setattr(
        "daily_bread.build_reading_messages",
        lambda *a, **kw: ["reading message"],
    )

    import daily_bread
    daily_bread.main()

    assert "111" in sent_to


def test_main_does_not_send_to_non_matching_hour(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=9)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    sent_to = []

    def mock_send(chat_id, messages, **kwargs):
        sent_to.append(str(chat_id))
        return True

    monkeypatch.setattr("daily_bread.send_messages", mock_send)
    monkeypatch.setattr(
        "daily_bread.get_reference_for_today",
        lambda today: (1, "Monday", "Gen 1"),
    )
    monkeypatch.setattr(
        "daily_bread.fetch_bible_text",
        lambda ref: ("Gen 1", [("1", "In the beginning God created...")]),
    )
    monkeypatch.setattr(
        "daily_bread.build_reading_messages",
        lambda *a, **kw: ["reading message"],
    )

    import daily_bread
    daily_bread.main()

    assert "111" in sent_to
    assert "222" not in sent_to


def test_main_includes_reflection_message_before_footer(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    sent_messages = []

    def mock_send(chat_id, messages, **kwargs):
        sent_messages.extend(messages)
        return True

    monkeypatch.setattr("daily_bread.send_messages", mock_send)
    monkeypatch.setattr(
        "daily_bread.get_reference_for_today",
        lambda today: (1, "Monday", "Gen 1"),
    )
    monkeypatch.setattr(
        "daily_bread.fetch_bible_text",
        lambda ref: ("Gen 1", [("1", "In the beginning God created...")]),
    )
    monkeypatch.setattr(
        "daily_bread.build_reading_messages",
        lambda *a, **kw: ["reading message", "footer"],
    )
    monkeypatch.setattr("daily_bread.prompt_for_date", lambda day: "Test prompt?")

    import daily_bread
    daily_bread.main()

    assert sent_messages[-1] == "footer"
    assert "Test prompt?" in sent_messages[-2]
