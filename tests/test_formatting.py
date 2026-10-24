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


# --- week listing ---

WEEK_ROWS = [
    ("Sunday", "I Cor 11-12"),
    ("Monday", "Exo 1-4"),
    ("Tuesday", "I Sam 16-20"),
    ("Wednesday", "Psalms 39-41"),
    ("Thursday", "Job 27-28"),
    ("Friday", "Jer 7-11"),
    ("Saturday", "Mark 7-8"),
]


def test_build_week_message_numbers_days_from_sunday():
    from formatting import build_week_message
    out = build_week_message(14, WEEK_ROWS)
    assert "Week 14" in out
    assert "Day 1" in out and "Sunday" in out and "I Cor 11-12" in out
    assert "Day 2" in out and "Exo 1-4" in out
    assert "Day 7" in out and "Mark 7-8" in out
    assert "Day 8" not in out


def test_build_week_message_lists_days_in_order():
    from formatting import build_week_message
    lines = build_week_message(14, WEEK_ROWS).splitlines()[1:]
    assert [line.split()[1] for line in lines] == [str(n) for n in range(1, 8)]


def test_build_week_message_marks_today_when_given():
    from formatting import build_week_message
    out = build_week_message(14, WEEK_ROWS, today_day_name="Wednesday")
    today_line = [ln for ln in out.splitlines() if "Wednesday" in ln][0]
    assert "today" in today_line
    assert out.count("today") == 1


def test_build_week_message_omits_marker_without_today():
    from formatting import build_week_message
    assert "today" not in build_week_message(14, WEEK_ROWS)


def test_build_week_message_handles_a_missing_reference():
    from formatting import build_week_message
    rows = [(name, None if name == "Friday" else ref) for name, ref in WEEK_ROWS]
    out = build_week_message(14, rows)
    friday = [ln for ln in out.splitlines() if "Friday" in ln][0]
    assert "—" in friday


def test_build_week_message_escapes_the_reference():
    from formatting import build_week_message
    out = build_week_message(1, [("Sunday", "Gen <1>")] )
    assert "&lt;1&gt;" in out
    assert "<1>" not in out
