"""52-week reading plan lookup by date."""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from config import PLAN_FILE, TIMEZONE

PLAN_WEEKS = 52

# The plan's own order, which is how plan.json lists every week: it starts on
# Sunday, not Monday. Each weekday carries a theme, so the order is meaningful
# rather than arbitrary, and the theme is what readers navigate by.
DAY_THEMES = {
    "Sunday": "Epistles",
    "Monday": "The Law",
    "Tuesday": "History",
    "Wednesday": "Psalms",
    "Thursday": "Poetry",
    "Friday": "Prophecy",
    "Saturday": "Gospels",
}

DAY_ORDER = tuple(DAY_THEMES)

DAY_MAP = {
    6: "Sunday",  # Epistles
    0: "Monday",  # The Law
    1: "Tuesday",  # History
    2: "Wednesday",  # Psalms
    3: "Thursday",  # Poetry
    4: "Friday",  # Prophecy
    5: "Saturday",  # Gospels
}


def get_eat_today() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def get_eat_now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


@lru_cache(maxsize=1)
def load_plan() -> dict:
    if not PLAN_FILE.exists():
        print(f"❌ {PLAN_FILE} not found!")
        return {}
    with PLAN_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def plan_week_for_date(day: date) -> int:
    """Plan week 1-52 for a calendar date, cycling from the ISO week number."""
    return ((day.isocalendar()[1] - 1) % PLAN_WEEKS) + 1


def get_week_references(plan_week: int) -> list[tuple[str, str | None]]:
    """Return [(day_name, reference)] for a plan week, in the plan's own order.

    Reads plan.json only. No passage text is fetched, so this costs nothing
    against the bible-api rate limit however often it is called.
    """
    week = load_plan().get(str(plan_week)) or {}
    return [(name, week.get(name) or None) for name in DAY_ORDER]


def get_reference_for_date(day: date) -> tuple[int, str | None, str | None]:
    """
    Return (plan_week, day_name, reference) for a calendar date.

    plan_week cycles 1–52 from ISO week number.
    """
    plan = load_plan()
    plan_week = plan_week_for_date(day)
    day_name = DAY_MAP.get(day.weekday())
    week_key = str(plan_week)

    if day_name and week_key in plan and day_name in plan[week_key]:
        return plan_week, day_name, plan[week_key][day_name]
    return plan_week, day_name, None


def get_reference_for_today(
    today: date | None = None,
) -> tuple[int, str | None, str | None]:
    return get_reference_for_date(today or get_eat_today())
