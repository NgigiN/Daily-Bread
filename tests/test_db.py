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
