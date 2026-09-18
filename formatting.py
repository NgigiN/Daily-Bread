"""Telegram HTML message building (shared by cron and bot)."""

from __future__ import annotations

import html

from config import MAX_MESSAGE_LEN

FOOTER = "---\n<i>Made with Love by Sam• Text via bible-api.com</i>"


def split_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip()
    return chunks


def _chapter_heading(chapter_ref: str, continued: bool = False) -> str:
    ref = html.escape(chapter_ref)
    if continued:
        return f"<b>{ref}</b> <i>(continued)</i>\n\n"
    return f"<b>{ref}</b>\n\n"


def build_chapter_messages(chapter_ref: str, chapter_text: str) -> list[str]:
    heading = _chapter_heading(chapter_ref)
    continued_heading = _chapter_heading(chapter_ref, continued=True)
    text_limit = MAX_MESSAGE_LEN - len(continued_heading)

    text_chunks = split_message(chapter_text, text_limit)
    messages: list[str] = []
    for index, chunk in enumerate(text_chunks):
        current = heading if index == 0 else continued_heading
        messages.append(current + chunk)
    return messages


def build_passage_messages(
    title: str,
    returned_ref: str,
    chapters: list[tuple[str, str]],
    *,
    include_footer: bool = True,
) -> list[str]:
    """Generic header + chapter bodies (+ optional footer)."""
    ref = html.escape(returned_ref)
    messages = [f"{title}\n\n<b>{ref}</b>"]
    for chapter_ref, chapter_text in chapters:
        messages.extend(build_chapter_messages(chapter_ref, chapter_text))
    if include_footer:
        messages.append(FOOTER)
    return messages


def build_reading_messages(
    plan_week: int,
    day_name: str,
    returned_ref: str,
    chapters: list[tuple[str, str]],
    *,
    date_label: str | None = None,
) -> list[str]:
    if date_label:
        title = (
            f"📖 <b>52-Week Bible Reading Plan</b>\n"
            f"<b>{date_label}</b>\n"
            f"<b>Week {plan_week} • {html.escape(day_name)}</b>"
        )
    else:
        title = (
            f"📖 <b>52-Week Bible Reading Plan</b>\n"
            f"<b>Week {plan_week} • {html.escape(day_name)}</b>"
        )
    return build_passage_messages(title, returned_ref, chapters)


def build_verse_messages(returned_ref: str, text: str) -> list[str]:
    return build_chapter_messages(returned_ref, text) + [FOOTER]


def build_reflection_message(prompt: str) -> str:
    return f"🤔 <b>Reflect</b>\n{html.escape(prompt)}"
