#!/usr/bin/env python3
"""Hourly cron entrypoint: nudge subscribers who haven't interacted today.

Reuses the existing hourly cron trigger. For each subscriber whose
(hour_eat + NUDGE_DELAY_HOURS) % 24 matches the current EAT hour, and who
has no activity logged today and hasn't already been nudged today, send one
gentle reminder.
"""

from __future__ import annotations

from datetime import timedelta

from config import NUDGE_DELAY_HOURS, NUDGE_IDLE_DAYS
from db import get_subscribers_for_nudge, record_nudge
from logutil import log_event
from plan_reader import get_eat_now, get_eat_today
from telegram_client import send_messages

NUDGE_MESSAGE = (
    "👋 Haven't seen you yet today — your reading's still there whenever "
    "you're ready. No pressure, just a nudge. 🙏\n\n"
    "<i>Rather not be reminded? <code>/nudge off</code> stops these and keeps "
    "your daily reading.</i>"
)


def main() -> None:
    hour = get_eat_now().hour
    today_date = get_eat_today()
    today = today_date.isoformat()
    active_since = (today_date - timedelta(days=NUDGE_IDLE_DAYS)).isoformat()

    subscribers = get_subscribers_for_nudge(
        current_hour=hour,
        delay_hours=NUDGE_DELAY_HOURS,
        activity_date=today,
        nudge_date=today,
        active_since=active_since,
    )
    if not subscribers:
        log_event("nudge_none_due", hour=hour, active_since=active_since)
        return

    sent = 0
    for sub in subscribers:
        chat_id = sub["chat_id"]
        if send_messages(chat_id, NUDGE_MESSAGE):
            record_nudge(chat_id, today)
            sent += 1

    log_event(
        "nudge_sent",
        sent=sent,
        total=len(subscribers),
        hour=hour,
        active_since=active_since,
    )


if __name__ == "__main__":
    main()
