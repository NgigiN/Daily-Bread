"""Telegram command parsing and handlers. Returns HTML message lists."""

from __future__ import annotations

import calendar
import html
import re
from datetime import date
from typing import Callable

from bible_client import (
    chapter_span_too_large,
    fetch_bible_text,
    fetch_verse_reference,
    parse_reference,
)
from config import MAX_CHAPTERS_PER_REQUEST
from db import add_subscriber, get_streak, get_subscriber, remove_subscriber, set_delivery_hour
from formatting import (
    build_passage_messages,
    build_reading_messages,
    build_reflection_message,
    build_verse_messages,
)
from plan_reader import get_eat_now, get_eat_today, get_reference_for_date
from prompts import prompt_for_date

# /command or /command@BotName, optional args
COMMAND_RE = re.compile(r"^/([a-zA-Z0-9_]+)(?:@\w+)?(?:\s+(.*))?$", re.DOTALL)
DAY_ARGS_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)$")

HELP_TEXT = """📖 <b>Daily Bread Bot</b>

<b>Reading commands</b>
/today - today's reading (52-week plan)
/day 17 may - reading for a date (current year)
/verse John 3:16 - a verse or range
/chapter John 3 - a full chapter (or Rom 1-2)

<b>Daily delivery</b>
/subscribe - get the daily reading (default 6am EAT)
/subscribe 8 - subscribe with 8am delivery
/settime 9 - change your delivery hour
/unsubscribe - stop daily readings
/streak - see your current and longest streak

/help - this message

<b>Examples</b>
• <code>/verse Jn 3:16</code>
• <code>/verse Matt 25:31-33</code>
• <code>/chapter Psalms 23</code>
• <code>/chapter Rom 1-2</code>
• <code>/day 17 may</code>

Tip: book names may be abbreviated (Jn, Rom, I Cor).
Max {max_ch} chapters per /chapter request.
Text via bible-api.com (WEB).""".format(max_ch=MAX_CHAPTERS_PER_REQUEST)

START_TEXT = """📖 <b>Welcome to Daily Bread</b>

Read the Bible with the 52-week plan, or look up any verse.

/today - today's reading
/day 17 may - reading for a date
/verse John 3:16 - a verse
/chapter John 3 - a chapter
/help - full help

Made with Love by Sam"""

BOT_COMMANDS = [
    {"command": "start", "description": "Welcome and command list"},
    {"command": "help", "description": "Full help and examples"},
    {"command": "today", "description": "Today's plan reading"},
    {"command": "day", "description": "Reading for a date, e.g. 17 may"},
    {"command": "verse", "description": "Look up a verse, e.g. John 3:16"},
    {"command": "chapter", "description": "Look up a chapter, e.g. John 3"},
    {"command": "subscribe", "description": "Get daily readings (e.g. /subscribe 8 for 8am)"},
    {"command": "unsubscribe", "description": "Stop daily readings"},
    {"command": "settime", "description": "Change delivery hour, e.g. /settime 9"},
    {"command": "streak", "description": "See your current and longest reading streak"},
]

MONTH_ALIASES: dict[str, int] = {}
for _i, _name in enumerate(calendar.month_name):
    if _name:
        MONTH_ALIASES[_name.lower()] = _i
for _i, _name in enumerate(calendar.month_abbr):
    if _name:
        MONTH_ALIASES[_name.lower()] = _i


def parse_command(text: str) -> tuple[str, str] | None:
    """Return (command_name_lower, args) or None if not a command."""
    text = (text or "").strip()
    match = COMMAND_RE.match(text)
    if not match:
        return None
    return match.group(1).lower(), (match.group(2) or "").strip()


def parse_day_args(args: str) -> date | str:
    """
    Parse '17 may' into a date in the current EAT year.
    Returns date on success, or an error string.
    """
    args = args.strip()
    if not args:
        return "Usage: <code>/day 17 may</code> (day + month, current year)"

    match = DAY_ARGS_RE.match(args)
    if not match:
        return "Could not parse date. Use: <code>/day 17 may</code>"

    day_num = int(match.group(1))
    month_key = match.group(2).lower()
    month = MONTH_ALIASES.get(month_key)
    if month is None:
        return f'Unknown month "{match.group(2)}". Try e.g. may, jan, january.'

    year = get_eat_now().year
    try:
        return date(year, month, day_num)
    except ValueError:
        return f"Invalid date: {day_num} {match.group(2)} {year}."


def _parse_hour(args: str) -> int | str:
    """Return int 0-23 on success, or an HTML error string."""
    args = args.strip()
    if not args:
        return "Please provide an hour, e.g. <code>/settime 9</code>."
    try:
        hour = int(args)
    except ValueError:
        return (
            f'"{html.escape(args)}" isn\'t a number. '
            "Please give an hour 0–23, e.g. <code>/settime 9</code>."
        )
    if not 0 <= hour <= 23:
        return "Please give an hour between 0 and 23, e.g. <code>/settime 9</code>."
    return hour


def _reading_for_date(day: date, *, date_label: str | None = None) -> list[str]:
    plan_week, day_name, ref = get_reference_for_date(day)
    if not ref or not day_name:
        return [
            f"No reading configured for week {plan_week}"
            + (f" - {day_name}" if day_name else "")
            + "."
        ]

    returned_ref, chapters = fetch_bible_text(ref)
    if not chapters:
        return [f"Could not load reading for <b>{ref}</b>."]

    assert returned_ref is not None
    messages = build_reading_messages(
        plan_week,
        day_name,
        returned_ref,
        chapters,
        date_label=date_label,
    )
    messages.insert(-1, build_reflection_message(prompt_for_date(day)))
    return messages


def handle_start(_args: str, chat_id: str = "") -> list[str]:
    return [START_TEXT]


def handle_help(_args: str, chat_id: str = "") -> list[str]:
    return [HELP_TEXT]


def handle_today(_args: str, chat_id: str = "") -> list[str]:
    today = get_eat_today()
    return _reading_for_date(today)


def handle_day(args: str, chat_id: str = "") -> list[str]:
    parsed = parse_day_args(args)
    if isinstance(parsed, str):
        return [parsed]
    label = parsed.strftime("%d %B %Y")
    return _reading_for_date(parsed, date_label=label)


def handle_verse(args: str, chat_id: str = "") -> list[str]:
    if not args:
        return ["Usage: <code>/verse John 3:16</code> (include chapter:verse)"]
    if ":" not in args:
        return [
            "Verse references need a colon, e.g. <code>/verse John 3:16</code>.\n"
            "For a full chapter use <code>/chapter John 3</code>."
        ]
    result = fetch_verse_reference(args)
    if result is None:
        return [
            f'Could not find "{args}". Check the book name and reference.'
        ]
    returned_ref, text = result
    return build_verse_messages(returned_ref, text)


def handle_chapter(args: str, chat_id: str = "") -> list[str]:
    if not args:
        return ["Usage: <code>/chapter John 3</code> or <code>/chapter Rom 1-2</code>"]

    book, start, end = parse_reference(args)
    if start is None:
        return [
            "Include a chapter number, e.g. <code>/chapter John 3</code>.\n"
            f"Whole books are limited to {MAX_CHAPTERS_PER_REQUEST} chapters; "
            "use a range if needed."
        ]

    if chapter_span_too_large(args):
        return [
            f"Please request at most {MAX_CHAPTERS_PER_REQUEST} chapters at a time "
            f"(bible-api.com rate limits)."
        ]

    # Cap whole-book style if someone passes only book via odd paths
    returned_ref, chapters = fetch_bible_text(
        args,
        max_chapters=MAX_CHAPTERS_PER_REQUEST,
    )
    if chapters is None:
        return [
            f"Please request at most {MAX_CHAPTERS_PER_REQUEST} chapters at a time."
        ]
    if not chapters or (
        len(chapters) == 1 and "Could not fetch text" in chapters[0][1]
    ):
        return [f'Could not find "{args}". Check the book name and chapter.']

    assert returned_ref is not None
    return build_passage_messages(
        "📖 <b>Bible chapter</b>", returned_ref, chapters
    )


def handle_subscribe(args: str, chat_id: str = "") -> list[str]:
    hour = 6
    if args.strip():
        result = _parse_hour(args)
        if isinstance(result, str):
            return [result]
        hour = result

    existing = get_subscriber(chat_id)
    if existing is not None:
        return [
            f"You're already subscribed (delivery at {existing['hour_eat']}:00 EAT). "
            "Use /settime to change your hour, or /unsubscribe to stop."
        ]

    add_subscriber(chat_id, hour_eat=hour)
    return [
        f"✅ You're subscribed! You'll get your daily reading at {hour}:00 EAT. "
        "Change your time with /settime, or /unsubscribe to stop."
    ]


def handle_unsubscribe(_args: str, chat_id: str = "") -> list[str]:
    removed = remove_subscriber(chat_id)
    if removed:
        return ["You've been unsubscribed. Send /subscribe any time to rejoin. 🙏"]
    return ["You weren't subscribed. Send /subscribe to sign up for daily readings."]


def handle_settime(args: str, chat_id: str = "") -> list[str]:
    result = _parse_hour(args)
    if isinstance(result, str):
        return [result]
    hour = result

    if get_subscriber(chat_id) is None:
        return [
            "You're not subscribed yet. "
            "Send /subscribe first to sign up for daily readings."
        ]

    set_delivery_hour(chat_id, hour)
    return [f"✅ Updated! You'll now get your daily reading at {hour}:00 EAT."]


def handle_streak(_args: str, chat_id: str = "") -> list[str]:
    if get_subscriber(chat_id) is None:
        return ["You're not subscribed yet. Send /subscribe to start building a streak."]

    current, longest, total = get_streak(chat_id, get_eat_today())
    return [
        "🔥 <b>Your streak</b>\n"
        f"Current: {current} day{'s' if current != 1 else ''}\n"
        f"Longest: {longest} day{'s' if longest != 1 else ''}\n"
        f"Total days active: {total}"
    ]


HANDLERS: dict[str, Callable[[str, str], list[str]]] = {
    "start": handle_start,
    "help": handle_help,
    "today": handle_today,
    "day": handle_day,
    "verse": handle_verse,
    "chapter": handle_chapter,
    "subscribe": handle_subscribe,
    "unsubscribe": handle_unsubscribe,
    "settime": handle_settime,
    "streak": handle_streak,
}


def handle_message_text(text: str, chat_id: str = "") -> list[str] | None:
    """
    Route a message body to a command handler.
    Returns message list, or None if the text is not a known command.
    """
    parsed = parse_command(text)
    if parsed is None:
        return None
    name, args = parsed
    handler = HANDLERS.get(name)
    if handler is None:
        return [
            f"Unknown command /{name}. Try /help for the list of commands."
        ]
    return handler(args, chat_id)
