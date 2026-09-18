"""Tests for bot_app.py webhook helpers."""

from __future__ import annotations


def test_extract_reaction_chat_id_present():
    from bot_app import _extract_reaction_chat_id
    update = {
        "message_reaction": {
            "chat": {"id": 555},
            "message_id": 10,
            "date": 1234567890,
            "old_reaction": [],
            "new_reaction": [{"type": "emoji", "emoji": "🙏"}],
        }
    }
    assert _extract_reaction_chat_id(update) == 555


def test_extract_reaction_chat_id_absent():
    from bot_app import _extract_reaction_chat_id
    assert _extract_reaction_chat_id({"message": {}}) is None


def test_extract_reaction_chat_id_missing_chat():
    from bot_app import _extract_reaction_chat_id
    assert _extract_reaction_chat_id({"message_reaction": {}}) is None
