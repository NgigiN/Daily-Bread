"""Tests for formatting.py message builders."""

from __future__ import annotations


def test_build_reflection_message_includes_prompt_text():
    from formatting import build_reflection_message
    msg = build_reflection_message("What stood out to you today?")
    assert "What stood out to you today?" in msg


def test_build_reflection_message_escapes_html():
    from formatting import build_reflection_message
    msg = build_reflection_message("Is <b>this</b> safe?")
    assert "<b>this</b>" not in msg
    assert "&lt;b&gt;this&lt;/b&gt;" in msg


def test_build_reflection_message_has_reflect_label():
    from formatting import build_reflection_message
    msg = build_reflection_message("A prompt")
    assert "Reflect" in msg
