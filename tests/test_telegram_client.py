"""Tests for send_messages retry behaviour."""

from __future__ import annotations

import pytest
import requests

TOKEN = "TESTTOKEN"


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = {"ok": status_code < 400} if body is None else body
        self.content = b"{}"

    def json(self) -> dict:
        return self._body


@pytest.fixture
def no_sleep(monkeypatch):
    """Record sleeps instead of taking them."""
    import telegram_client

    slept: list[float] = []
    monkeypatch.setattr(telegram_client.time, "sleep", lambda s: slept.append(s))
    return slept


def _patch_post(monkeypatch, responses):
    """Serve `responses` in order; raise if they run out. Records each payload."""
    import telegram_client

    calls: list[dict] = []
    queue = list(responses)

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        assert queue, "requests.post called more times than expected"
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(telegram_client.requests, "post", fake_post)
    return calls


def test_transient_5xx_is_retried_then_succeeds(monkeypatch, no_sleep):
    from telegram_client import send_messages

    calls = _patch_post(
        monkeypatch, [FakeResponse(503), FakeResponse(503), FakeResponse(200)]
    )

    assert send_messages("111", "hello", token=TOKEN) is True
    assert len(calls) == 3
    # the same chunk each time — a retry must not advance past the failed chunk
    assert {c["text"] for c in calls} == {"hello"}


def test_permanent_4xx_is_not_retried(monkeypatch, no_sleep):
    from telegram_client import send_messages

    calls = _patch_post(
        monkeypatch,
        [FakeResponse(403, {"ok": False, "description": "bot was blocked by the user"})],
    )

    assert send_messages("111", "hello", token=TOKEN) is False
    assert len(calls) == 1
    assert no_sleep == []


def test_gives_up_after_max_attempts(monkeypatch, no_sleep):
    from config import SEND_MAX_ATTEMPTS
    from telegram_client import send_messages

    calls = _patch_post(
        monkeypatch, [FakeResponse(503) for _ in range(SEND_MAX_ATTEMPTS)]
    )

    assert send_messages("111", "hello", token=TOKEN) is False
    assert len(calls) == SEND_MAX_ATTEMPTS


def test_backoff_grows_between_attempts(monkeypatch, no_sleep):
    from config import SEND_RETRY_BASE_SEC
    from telegram_client import send_messages

    _patch_post(monkeypatch, [FakeResponse(503), FakeResponse(503), FakeResponse(200)])
    send_messages("111", "hello", token=TOKEN)

    # two retries happened, so two backoff sleeps, each longer than the last
    backoffs = [s for s in no_sleep if s >= SEND_RETRY_BASE_SEC]
    assert backoffs == [SEND_RETRY_BASE_SEC, SEND_RETRY_BASE_SEC * 2]


def test_429_honours_retry_after(monkeypatch, no_sleep):
    from telegram_client import send_messages

    _patch_post(
        monkeypatch,
        [
            FakeResponse(429, {"ok": False, "parameters": {"retry_after": 7}}),
            FakeResponse(200),
        ],
    )

    assert send_messages("111", "hello", token=TOKEN) is True
    assert 7 in no_sleep


def test_429_retry_after_is_capped(monkeypatch, no_sleep):
    from config import SEND_RETRY_MAX_SLEEP_SEC
    from telegram_client import send_messages

    _patch_post(
        monkeypatch,
        [
            FakeResponse(429, {"ok": False, "parameters": {"retry_after": 9999}}),
            FakeResponse(200),
        ],
    )

    assert send_messages("111", "hello", token=TOKEN) is True
    assert max(no_sleep) == SEND_RETRY_MAX_SLEEP_SEC


def test_network_error_is_retried(monkeypatch, no_sleep):
    from telegram_client import send_messages

    calls = _patch_post(
        monkeypatch,
        [requests.ConnectionError("connection reset"), FakeResponse(200)],
    )

    assert send_messages("111", "hello", token=TOKEN) is True
    assert len(calls) == 2


def test_network_error_exhausts_attempts(monkeypatch, no_sleep):
    from config import SEND_MAX_ATTEMPTS
    from telegram_client import send_messages

    calls = _patch_post(
        monkeypatch,
        [requests.Timeout("timed out") for _ in range(SEND_MAX_ATTEMPTS)],
    )

    assert send_messages("111", "hello", token=TOKEN) is False
    assert len(calls) == SEND_MAX_ATTEMPTS


def test_retry_does_not_resend_earlier_messages(monkeypatch, no_sleep):
    """A later failure must not cause an already-accepted message to repeat."""
    from telegram_client import send_messages

    calls = _patch_post(
        monkeypatch, [FakeResponse(200), FakeResponse(503), FakeResponse(200)]
    )

    assert send_messages("111", ["first", "second"], token=TOKEN) is True
    assert [c["text"] for c in calls] == ["first", "second", "second"]


def test_unsuccessful_200_is_not_retried(monkeypatch, no_sleep):
    """HTTP 200 with ok=false is a protocol error, not something to repeat."""
    from telegram_client import send_messages

    calls = _patch_post(
        monkeypatch, [FakeResponse(200, {"ok": False, "description": "nope"})]
    )

    assert send_messages("111", "hello", token=TOKEN) is False
    assert len(calls) == 1


def test_placeholder_token_still_short_circuits(monkeypatch, no_sleep):
    from telegram_client import send_messages

    calls = _patch_post(monkeypatch, [])
    assert send_messages("111", "hello", token="123456789:placeholder") is False
    assert calls == []
