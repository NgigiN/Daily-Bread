"""Tests for prompts.py reflection prompt bank."""

from __future__ import annotations

from datetime import date, timedelta


def test_prompt_for_date_returns_a_bank_entry():
    from prompts import REFLECTION_PROMPTS, prompt_for_date
    result = prompt_for_date(date(2026, 9, 18))
    assert result in REFLECTION_PROMPTS


def test_prompt_for_date_is_deterministic():
    from prompts import prompt_for_date
    d = date(2026, 9, 18)
    assert prompt_for_date(d) == prompt_for_date(d)


def test_prompt_for_date_varies_by_day_of_year():
    from prompts import prompt_for_date
    assert prompt_for_date(date(2026, 1, 1)) != prompt_for_date(date(2026, 1, 2))


def test_prompt_bank_has_at_least_40_entries():
    from prompts import REFLECTION_PROMPTS
    assert len(REFLECTION_PROMPTS) >= 40


def test_prompt_for_date_wraps_around_bank_length():
    from prompts import REFLECTION_PROMPTS, prompt_for_date
    bank_len = len(REFLECTION_PROMPTS)
    d1 = date(2026, 1, 1)
    d2 = d1 + timedelta(days=bank_len)
    assert prompt_for_date(d1) == prompt_for_date(d2)
