"""Telegram command parsing and handlers. Returns HTML message lists."""

from __future__ import annotations

import calendar
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
from formatting import (
    build_passage_messages,
    build_reading_messages,
    build_verse_messages,
)
from plan_reader import get_eat_now, get_eat_today, get_reference_for_date

# /command or /command@BotName, optional args
COMMAND_RE = re.compile(r"^/([a-zA-Z0-9_]+)(?:@\w+)?(?:\s+(.*))?$", re.DOTALL)
DAY_ARGS_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)$")

HELP_TEXT = """📖 <b>Daily Bread Bot</b>

<b>Commands</b>
/today — today's reading (52-week plan)
/day 17 may — reading for a date (current year)
/verse John 3:16 — a verse or range
/chapter John 3 — a full chapter (or Rom 1-2)
/help — this message

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

/today — today's reading
/day 17 may — reading for a date
/verse John 3:16 — a verse
/chapter John 3 — a chapter
/help — full help

Made with Love by Sam"""

BOT_COMMANDS = [
    {"command": "start", "description": "Welcome and command list"},
    {"command": "help", "description": "Full help and examples"},
    {"command": "today", "description": "Today's plan reading"},
    {"command": "day", "description": "Reading for a date, e.g. 17 may"},
    {"command": "verse", "description": "Look up a verse, e.g. John 3:16"},
    {"command": "chapter", "description": "Look up a chapter, e.g. John 3"},
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
        return f"Unknown month “{match.group(2)}”. Try e.g. may, jan, january."

    year = get_eat_now().year
    try:
        return date(year, month, day_num)
    except ValueError:
        return f"Invalid date: {day_num} {match.group(2)} {year}."


def _reading_for_date(day: date, *, date_label: str | None = None) -> list[str]:
    plan_week, day_name, ref = get_reference_for_date(day)
    if not ref or not day_name:
        return [
            f"No reading configured for week {plan_week}"
            + (f" — {day_name}" if day_name else "")
            + "."
        ]

    returned_ref, chapters = fetch_bible_text(ref)
    if not chapters:
        return [f"Could not load reading for <b>{ref}</b>."]

    assert returned_ref is not None
    return build_reading_messages(
        plan_week,
        day_name,
        returned_ref,
        chapters,
        date_label=date_label,
    )


def handle_start(_args: str) -> list[str]:
    return [START_TEXT]


def handle_help(_args: str) -> list[str]:
    return [HELP_TEXT]


def handle_today(_args: str) -> list[str]:
    today = get_eat_today()
    return _reading_for_date(today)


def handle_day(args: str) -> list[str]:
    parsed = parse_day_args(args)
    if isinstance(parsed, str):
        return [parsed]
    label = parsed.strftime("%d %B %Y")
    return _reading_for_date(parsed, date_label=label)


def handle_verse(args: str) -> list[str]:
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
            f"Could not find “{args}”. Check the book name and reference."
        ]
    returned_ref, text = result
    return build_verse_messages(returned_ref, text)


def handle_chapter(args: str) -> list[str]:
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
        return [f"Could not find “{args}”. Check the book name and chapter."]

    assert returned_ref is not None
    return build_passage_messages(
        "📖 <b>Bible chapter</b>", returned_ref, chapters
    )


HANDLERS: dict[str, Callable[[str], list[str]]] = {
    "start": handle_start,
    "help": handle_help,
    "today": handle_today,
    "day": handle_day,
    "verse": handle_verse,
    "chapter": handle_chapter,
}


def handle_message_text(text: str) -> list[str] | None:
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
    return handler(args)
