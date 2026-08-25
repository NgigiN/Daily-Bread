#!/usr/bin/env python3
"""Daily cron entrypoint: push today plan reading to subscribed chats.

Cron fires every hour (top of hour). This script queries the subscriber DB
for chat_ids whose delivery hour matches the current EAT hour, then sends.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bible_client import fetch_bible_text
from config import TIMEZONE
from db import get_subscribers_for_hour
from formatting import build_reading_messages
from logutil import log_event
from plan_reader import get_eat_today, get_reference_for_today
from telegram_client import send_messages


def _get_current_hour_eat() -> int:
    return datetime.now(ZoneInfo(TIMEZONE)).hour


def _get_recipients() -> list[str]:
    return get_subscribers_for_hour(_get_current_hour_eat())


def _dispatch_log(msg: str, **fields: Any) -> None:
    log_event(msg, **fields)
    line = json.dumps({"msg": msg, **fields}, separators=(",", ":"), default=str)
    try:
        with open("/proc/1/fd/1", "a") as fh:
            fh.write(line + "\n")
            fh.flush()
    except OSError:
        pass


def main() -> None:
    chat_ids = _get_recipients()
    hour = _get_current_hour_eat()

    if not chat_ids:
        _dispatch_log("dispatch_no_subscribers", hour=hour)
        return

    today = get_eat_today()
    plan_week, day_name, ref = get_reference_for_today(today)

    if not ref or not day_name:
        msg = f"No reading configured for week {plan_week}" + (
            f" — {day_name}" if day_name else ""
        )
        for chat_id in chat_ids:
            send_messages(chat_id, msg)
        return

    returned_ref, chapters = fetch_bible_text(ref)
    if not chapters or returned_ref is None:
        for chat_id in chat_ids:
            send_messages(chat_id, f"Could not load reading for {ref}.")
        return

    messages = build_reading_messages(plan_week, day_name, returned_ref, chapters)

    sent = 0
    for chat_id in chat_ids:
        if send_messages(chat_id, messages):
            sent += 1

    label = f"Week {plan_week} \u2022 {day_name}: {ref}"
    if sent:
        _dispatch_log("dispatch_sent", sent=sent, total=len(chat_ids), hour=hour, ref=label)
    else:
        _dispatch_log("dispatch_failed", sent=0, total=len(chat_ids), hour=hour, ref=label)


if __name__ == "__main__":
    main()
