#!/usr/bin/env python3
"""Daily cron entrypoint: push today's plan reading to TELEGRAM_CHAT_IDS.

Interactive commands live in bot_app.py; this script stays one-shot for cron.
"""

from __future__ import annotations

from bible_client import fetch_bible_text
from formatting import build_reading_messages
from plan_reader import get_eat_today, get_reference_for_today
from telegram_client import send_to_configured_chats


def main() -> None:
    today = get_eat_today()
    plan_week, day_name, ref = get_reference_for_today(today)

    if not ref or not day_name:
        msg = f"No reading configured for week {plan_week}" + (
            f" — {day_name}" if day_name else ""
        )
        send_to_configured_chats(msg)
        return

    returned_ref, chapters = fetch_bible_text(ref)
    if not chapters or returned_ref is None:
        send_to_configured_chats(f"Could not load reading for {ref}.")
        return

    messages = build_reading_messages(
        plan_week, day_name, returned_ref, chapters
    )

    if send_to_configured_chats(messages):
        print(f"✅ Sent successfully → Week {plan_week} • {day_name}: {ref}")
    else:
        print("❌ Failed to send to Telegram.")


if __name__ == "__main__":
    main()
