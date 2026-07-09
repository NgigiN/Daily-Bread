"""52-week reading plan lookup by date."""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from config import PLAN_FILE, TIMEZONE

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


def get_reference_for_date(day: date) -> tuple[int, str | None, str | None]:
    """
    Return (plan_week, day_name, reference) for a calendar date.

    plan_week cycles 1–52 from ISO week number.
    """
    plan = load_plan()
    week_num = day.isocalendar()[1]
    plan_week = ((week_num - 1) % 52) + 1
    day_name = DAY_MAP.get(day.weekday())
    week_key = str(plan_week)

    if day_name and week_key in plan and day_name in plan[week_key]:
        return plan_week, day_name, plan[week_key][day_name]
    return plan_week, day_name, None


def get_reference_for_today(
    today: date | None = None,
) -> tuple[int, str | None, str | None]:
    return get_reference_for_date(today or get_eat_today())
