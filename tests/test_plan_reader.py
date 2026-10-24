"""Tests for week-level plan lookup."""

from __future__ import annotations

from datetime import date


def test_day_order_starts_at_sunday_and_has_seven_days():
    from plan_reader import DAY_ORDER
    assert DAY_ORDER[0] == "Sunday"
    assert DAY_ORDER[-1] == "Saturday"
    assert len(DAY_ORDER) == 7


def test_day_order_matches_the_plan_file_key_order():
    """Day 1 is whatever the plan itself lists first, not Monday."""
    from plan_reader import DAY_ORDER, load_plan
    assert tuple(load_plan()["1"].keys()) == tuple(DAY_ORDER)


def test_get_week_references_returns_seven_pairs_in_plan_order():
    from plan_reader import DAY_ORDER, get_week_references
    rows = get_week_references(14)
    assert [name for name, _ in rows] == list(DAY_ORDER)


def test_get_week_references_reads_real_plan_data():
    from plan_reader import get_week_references
    rows = dict(get_week_references(14))
    assert rows["Sunday"] == "I Cor 11-12"
    assert rows["Monday"] == "Exo 1-4"
    assert rows["Saturday"] == "Mark 7-8"


def test_get_week_references_unknown_week_is_all_none():
    from plan_reader import get_week_references
    rows = get_week_references(999)
    assert len(rows) == 7
    assert all(ref is None for _, ref in rows)


def test_every_week_in_the_plan_is_complete():
    from plan_reader import get_week_references
    for week in range(1, 53):
        rows = get_week_references(week)
        missing = [name for name, ref in rows if not ref]
        assert not missing, f"week {week} missing {missing}"


def test_plan_week_for_date_stays_in_range():
    from plan_reader import PLAN_WEEKS, plan_week_for_date
    day = date(2026, 1, 1)
    for _ in range(400):
        assert 1 <= plan_week_for_date(day) <= PLAN_WEEKS
        day = date.fromordinal(day.toordinal() + 1)


def test_plan_week_for_date_agrees_with_single_day_lookup():
    from plan_reader import get_reference_for_date, plan_week_for_date
    day = date(2026, 4, 2)
    assert get_reference_for_date(day)[0] == plan_week_for_date(day)
