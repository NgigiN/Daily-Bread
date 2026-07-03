#!/usr/bin/env python3

import html
import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

PLAN_FILE = "plan.json"
BIBLE_API = "https://bible-api.com/"
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LEN = 4096
MAX_CHAPTERS = 150
VERSE_RANGE_END = 200
CHAPTER_SUFFIX = re.compile(r"^(.+?)\s+(\d+)(?:-(\d+))?$")
FETCH_DELAY_SEC = 0.5
MAX_FETCH_RETRIES = 4
SEND_DELAY_SEC = 0.35


def get_eat_today():
    eat = ZoneInfo("Africa/Nairobi")
    return datetime.now(eat).date()


def load_plan():
    if not os.path.exists(PLAN_FILE):
        print(f"❌ {PLAN_FILE} not found!")
        return {}
    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_reference_for_today(today):
    plan = load_plan()
    week_num = today.isocalendar()[1]
    plan_week = ((week_num - 1) % 52) + 1
    week_day = today.weekday()

    day_map = {
        6: "Sunday",  # Epistles
        0: "Monday",  # The Law
        1: "Tuesday",  # History
        2: "Wednesday",  # Psalms
        3: "Thursday",  # Poetry
        4: "Friday",  # Prophecy
        5: "Saturday",  # Gospels
    }

    day_name = day_map.get(week_day)
    week_key = str(plan_week)

    if week_key in plan and day_name in plan[week_key]:
        return plan_week, day_name, plan[week_key][day_name]
    return plan_week, day_name, None


def parse_reference(reference):
    reference = reference.strip()
    match = CHAPTER_SUFFIX.match(reference)
    if match:
        book = match.group(1).strip()
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        return book, start, end
    return reference.strip(), None, None


def _api_query(query):
    url = BIBLE_API + query.replace(" ", "+")
    for attempt in range(MAX_FETCH_RETRIES):
        r = requests.get(url, timeout=15)
        if r.status_code == 429:
            time.sleep(2**attempt)
            continue
        if r.status_code == 404:
            return {"error": "not found"}
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def _needs_verse_range(returned_ref, chapter):
    return re.search(rf"\b{chapter}:\d+\b", returned_ref) is not None


def _format_chapter_text(data):
    verses = data.get("verses")
    if verses:
        parts = []
        for verse in verses:
            text = verse.get("text", "").strip()
            if not text:
                continue
            parts.append(f"<b>{verse['verse']}</b> {html.escape(text)}")
        if parts:
            return "\n".join(parts)

    text = data.get("text", "").strip()
    return html.escape(text) if text else ""


def _fetch_chapter(book, chapter):
    query = f"{book} {chapter}"
    data = _api_query(query)
    if data.get("error"):
        return None

    returned_ref = data.get("reference", query)
    text = _format_chapter_text(data)
    if not text:
        return None

    if _needs_verse_range(returned_ref, chapter):
        data = _api_query(f"{book} {chapter}:1-{VERSE_RANGE_END}")
        if data.get("error"):
            return None
        returned_ref = data.get("reference", query)
        text = _format_chapter_text(data)
        if not text:
            return None

    return returned_ref, text


def fetch_bible_text(reference):
    if not reference:
        return None, None

    book, start, end = parse_reference(reference)
    chapters = []

    if start is not None:
        for chapter in range(start, end + 1):
            try:
                result = _fetch_chapter(book, chapter)
            except Exception as e:
                print(f"Fetch warning: {book} {chapter} failed ({e})")
                result = None
            if result is None:
                print(f"Fetch warning: missing {book} {chapter}")
                continue
            chapters.append(result)
            time.sleep(FETCH_DELAY_SEC)
    else:
        for chapter in range(1, MAX_CHAPTERS + 1):
            try:
                result = _fetch_chapter(book, chapter)
            except Exception as e:
                print(f"Fetch warning: {book} {chapter} failed ({e})")
                result = None
            if result is None:
                break
            chapters.append(result)
            time.sleep(FETCH_DELAY_SEC)

    if not chapters:
        return reference, [
            (
                reference,
                html.escape(
                    f"Could not fetch text. Please read {reference} on Bible.com or in your app."
                ),
            )
        ]

    return reference, chapters


def get_telegram_config():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    raw_ids = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
    chat_ids = [cid.strip() for cid in raw_ids.split(",") if cid.strip()]
    return token, chat_ids


def split_message(text, limit=MAX_MESSAGE_LEN):
    if len(text) <= limit:
        return [text]
    chunks = []
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


def _chapter_heading(chapter_ref, continued=False):
    ref = html.escape(chapter_ref)
    if continued:
        return f"<b>{ref}</b> <i>(continued)</i>\n\n"
    return f"<b>{ref}</b>\n\n"


def build_chapter_messages(chapter_ref, chapter_text):
    heading = _chapter_heading(chapter_ref)
    continued_heading = _chapter_heading(chapter_ref, continued=True)
    text_limit = MAX_MESSAGE_LEN - len(continued_heading)

    text_chunks = split_message(chapter_text, text_limit)
    messages = []
    for index, chunk in enumerate(text_chunks):
        current_heading = heading if index == 0 else continued_heading
        messages.append(current_heading + chunk)
    return messages


def build_reading_messages(plan_week, day_name, returned_ref, chapters):
    ref = html.escape(returned_ref)
    messages = [
        f"""📖 <b>52-Week Bible Reading Plan</b>
<b>Week {plan_week} • {day_name}</b>

<b>{ref}</b>"""
    ]

    for chapter_ref, chapter_text in chapters:
        messages.extend(build_chapter_messages(chapter_ref, chapter_text))

    messages.append(
        "---\n<i>Made with Love by Sam• Text via bible-api.com</i>"
    )
    return messages


def send_to_telegram(messages):
    token, chat_ids = get_telegram_config()
    if not token or token.startswith("123456789"):
        print("❌ Set TELEGRAM_BOT_TOKEN in .env")
        return False
    if not chat_ids:
        print("❌ Set TELEGRAM_CHAT_IDS in .env (run discover_chats.py)")
        return False

    if isinstance(messages, str):
        messages = [messages]

    url = TELEGRAM_API.format(token=token, method="sendMessage")
    sent_any = False

    for chat_id in chat_ids:
        try:
            for message in messages:
                chunks = split_message(message)
                for chunk in chunks:
                    r = requests.post(
                        url,
                        json={
                            "chat_id": chat_id,
                            "text": chunk,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True,
                        },
                        timeout=15,
                    )
                    r.raise_for_status()
                    body = r.json()
                    if not body.get("ok"):
                        print(f"❌ Telegram error for {chat_id}: {body}")
                        break
                    time.sleep(SEND_DELAY_SEC)
                else:
                    continue
                break
            else:
                sent_any = True
        except Exception as e:
            print(f"❌ Telegram send error for {chat_id}: {e}")

    return sent_any


def main():
    today = get_eat_today()
    plan_week, day_name, ref = get_reference_for_today(today)

    if not ref:
        msg = f"No reading configured for week {plan_week} — {day_name}"
        send_to_telegram(msg)
        return

    returned_ref, chapters = fetch_bible_text(ref)
    messages = build_reading_messages(plan_week, day_name, returned_ref, chapters)

    if send_to_telegram(messages):
        print(f"✅ Sent successfully → Week {plan_week} • {day_name}: {ref}")
    else:
        print("❌ Failed to send to Telegram.")


if __name__ == "__main__":
    main()
