# Devotional Companion — Design Spec

**Date:** 2026-09-18
**Status:** Approved for implementation

---

## Problem

The bot currently only delivers text: a reading, on a schedule, to whoever is subscribed. There's no sense of habit, no acknowledgement that the reading happened, and no prompt to actually engage with it beyond reading words on a screen. Nothing changes whether a subscriber reads every day or never opens the bot again.

---

## Goal

Turn the daily push into a devotional companion: send a short reflection prompt alongside each reading, track a real streak based on subscriber interaction, expose that streak via `/streak`, and send one gentle nudge to subscribers who haven't interacted by partway through their day.

---

## Out of Scope

- Journaling / storing reflection answers (explicitly deferred — this phase is prompts + streaks only, no text capture)
- LLM-generated, passage-specific prompts (static bank only; no new API dependency)
- Correlating a reply/reaction to the *specific* day's message — any interaction with the bot that day counts (see Design Decisions)
- Per-subscriber configurable nudge delay (fixed via `NUDGE_DELAY_HOURS` constant, same for everyone)
- Translation/language choice (separate spec — independent piece of work, not part of this one)
- Per-user timezone support (unchanged: all times Africa/Nairobi / EAT)
- A web admin interface or any non-Telegram surface

---

## Design Decisions

These were explicit trade-offs made during brainstorming, recorded so they read as decisions, not oversights:

- **"Any interaction counts" for streaks.** Sending `/help` keeps a streak alive without necessarily reading anything that day. This was chosen over reply-to-message correlation because it's simpler to build and verify, and it's a personal-scale bot for a known small circle — gaming your own streak isn't a real risk here.
- **Static prompt bank over LLM generation.** No new API dependency, no per-message cost or latency added to the hourly dispatch job, fully offline and deterministic (same prompt for everyone on a given day, which also makes it testable without mocking).
- **No journaling yet.** Keeps this phase to "prompt + streak," which is the smallest useful unit. Journaling (capture + `/myjournal` recall) is a natural follow-up once this is proven out, not bundled in here.
- **Nudge relative to delivery hour, not a fixed clock time.** A subscriber who reads at 6am and one who reads at 9pm shouldn't get nudged at the same fixed hour — the nudge should track their own rhythm.

---

## Data Model

Two new SQLite tables, additive only — no changes to the existing `subscribers` schema.

```sql
CREATE TABLE IF NOT EXISTS activity (
    chat_id        TEXT    NOT NULL,
    activity_date  TEXT    NOT NULL,
    first_seen_at  TEXT    NOT NULL,
    PRIMARY KEY (chat_id, activity_date)
);

CREATE TABLE IF NOT EXISTS nudges (
    chat_id     TEXT    NOT NULL,
    nudge_date  TEXT    NOT NULL,
    sent_at     TEXT    NOT NULL,
    PRIMARY KEY (chat_id, nudge_date)
);
```

| Table | Column | Notes |
|---|---|---|
| `activity` | `chat_id` | Telegram chat ID, same convention as `subscribers.chat_id` |
| `activity` | `activity_date` | `YYYY-MM-DD`, EAT calendar date. One row per chat per day — `INSERT OR IGNORE` makes logging idempotent |
| `activity` | `first_seen_at` | ISO-8601 UTC timestamp of the first qualifying interaction that day |
| `nudges` | `chat_id` / `nudge_date` | Composite PK prevents double-nudging the same subscriber on the same day |
| `nudges` | `sent_at` | ISO-8601 UTC timestamp the nudge was sent |

Both tables are created in the existing `init_db()` — safe to call on every startup, same as today.

---

## New File: `prompts.py`

Single-responsibility: the static reflection prompt bank and deterministic day-based selection. No I/O, no dependencies beyond stdlib.

```python
"""Static reflection prompt bank. Deterministic rotation by day-of-year."""

from __future__ import annotations

from datetime import date

REFLECTION_PROMPTS: list[str] = [
    "What verse or phrase stood out to you today, and why?",
    "Is there a promise in today's reading you can hold onto this week?",
    "What is this passage asking you to do differently?",
    "Who could you share today's reading with?",
    "What does today's reading reveal about God's character?",
    "Where do you see yourself in today's passage?",
    "What question would you ask if you could talk to the author?",
    "Is there a command here you've been putting off obeying?",
    "What's one word that sums up today's reading?",
    "How does today's reading challenge something you believe?",
    "What would change if you took today's passage seriously this week?",
    "Is there someone in today's reading you relate to? Why?",
    "What's a practical step you can take because of what you read?",
    "What surprised you in today's reading?",
    "How does today's passage connect to something happening in your life right now?",
    "What's something you're grateful for after reading this?",
    "Is there a warning in today's reading worth paying attention to?",
    "What does today's reading teach you about prayer?",
    "Where do you need more faith after reading this?",
    "What would you tell a friend who asked what today's reading was about?",
    "Is there a pattern of sin or struggle named here that you recognize in yourself?",
    "What does today's reading say about how to treat others?",
    "What's one thing you want to remember from today's reading a week from now?",
    "How does this passage point to Jesus?",
    "What emotion did today's reading stir in you?",
    "Is there an example here worth imitating?",
    "What's something you don't understand in today's reading — and who could you ask?",
    "How would your day be different if you lived out today's passage?",
    "What does today's reading show about God's faithfulness?",
    "Is there an idol or distraction today's passage is confronting?",
    "What's a prayer you could pray in response to today's reading?",
    "Who in today's reading needed courage, and where do you need it too?",
    "What's the hardest part of today's reading to accept?",
    "How does today's reading shape how you'll spend the next 24 hours?",
    "What does today's passage say is worth valuing?",
    "Is there a relationship in today's reading you can learn from?",
    "What's one thing today's reading asks you to let go of?",
    "How does today's reading encourage you?",
    "What's a way you could obey today's reading, specifically, before the day ends?",
    "If today's reading were the only Scripture you had, what would you take from it?",
]


def prompt_for_date(day: date) -> str:
    """Deterministic prompt for a calendar date — same prompt for everyone that day."""
    index = (day.timetuple().tm_yday - 1) % len(REFLECTION_PROMPTS)
    return REFLECTION_PROMPTS[index]
```

40 prompts means the rotation repeats roughly every 40 days rather than lining up with any weekly/monthly pattern — deliberate, so it doesn't feel mechanically tied to the calendar.

---

## Modified Files

### `db.py` — new functions

All functions stay pure persistence: no `plan_reader`/timezone imports. Callers pass EAT dates explicitly (mirrors how `daily_bread.py` already computes `hour_eat` and passes it to `get_subscribers_for_hour`).

```python
def record_activity(chat_id: str, activity_date: str) -> None:
    """Log an interaction for chat_id on activity_date (YYYY-MM-DD). Idempotent."""

def has_activity(chat_id: str, activity_date: str) -> bool:
    """True if chat_id has an activity row for activity_date."""

def get_streak(chat_id: str, today: date) -> tuple[int, int, int]:
    """
    Return (current_streak, longest_streak, total_days_active) for chat_id.

    current_streak is 0 if the most recent activity date isn't today or
    yesterday (i.e. the streak is broken as of `today`).
    """

def record_nudge(chat_id: str, nudge_date: str) -> None:
    """Log that a nudge was sent to chat_id on nudge_date. Idempotent."""

def get_subscribers_for_nudge(
    *, current_hour: int, delay_hours: int, activity_date: str, nudge_date: str
) -> list[dict[str, Any]]:
    """
    Return subscriber rows {chat_id, hour_eat} where:
      (hour_eat + delay_hours) % 24 == current_hour
      AND no activity row for activity_date
      AND no nudges row for nudge_date
    """
```

`get_streak` implementation sketch:

```python
from datetime import date, timedelta

def get_streak(chat_id: str, today: date) -> tuple[int, int, int]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT activity_date FROM activity WHERE chat_id = ? ORDER BY activity_date DESC",
            (chat_id,),
        ).fetchall()
    finally:
        conn.close()

    dates = [date.fromisoformat(row[0]) for row in rows]
    total = len(dates)
    if not dates:
        return 0, 0, 0

    current = 0
    if dates[0] in (today, today - timedelta(days=1)):
        current = 1
        for i in range(1, len(dates)):
            if dates[i - 1] - dates[i] == timedelta(days=1):
                current += 1
            else:
                break

    ascending = sorted(dates)
    longest = run = 1
    for i in range(1, len(ascending)):
        if ascending[i] - ascending[i - 1] == timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return current, longest, total
```

`get_subscribers_for_nudge` implementation sketch (SQLite supports `%` as modulo):

```python
def get_subscribers_for_nudge(
    *, current_hour: int, delay_hours: int, activity_date: str, nudge_date: str
) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT chat_id, hour_eat FROM subscribers
            WHERE (hour_eat + ?) % 24 = ?
              AND chat_id NOT IN (SELECT chat_id FROM activity WHERE activity_date = ?)
              AND chat_id NOT IN (SELECT chat_id FROM nudges WHERE nudge_date = ?)
            """,
            (delay_hours, current_hour, activity_date, nudge_date),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
```

`init_db()` gains the two `CREATE TABLE IF NOT EXISTS` statements for `activity` and `nudges`.

---

### `config.py`

```python
NUDGE_DELAY_HOURS = 8
```

Added near the other constants (`SEND_DELAY_SEC`, `CACHE_TTL_SEC`). Not exposed as an env var — fixed for all subscribers per the Out of Scope note.

---

### `formatting.py`

One new helper, following the existing pattern (HTML-escaped, returns a plain string for the caller to append to a messages list):

```python
def build_reflection_message(prompt: str) -> str:
    return f"🤔 <b>Reflect</b>\n{html.escape(prompt)}"
```

---

### `daily_bread.py`

After building the reading messages, insert the reflection message before the footer (footer is always `messages[-1]`, added by `build_passage_messages`):

```python
from prompts import prompt_for_date

messages = build_reading_messages(plan_week, day_name, returned_ref, chapters)
messages.insert(-1, build_reflection_message(prompt_for_date(today)))
```

Resulting order per subscriber: reading chapter(s) → reflection prompt → footer.

---

### `commands.py`

**`_reading_for_date` gains the same reflection insertion**, so `/today` and `/day` show the same day's prompt as the daily push — one code path, one behavior, instead of the push and the on-demand commands drifting apart:

```python
def _reading_for_date(day: date, *, date_label: str | None = None) -> list[str]:
    ...
    messages = build_reading_messages(plan_week, day_name, returned_ref, chapters, date_label=date_label)
    messages.insert(-1, build_reflection_message(prompt_for_date(day)))
    return messages
```

**New handler:**

```python
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
```

Add to `HANDLERS`:

```python
"streak": handle_streak,
```

Add to `BOT_COMMANDS`:

```python
{"command": "streak", "description": "See your current and longest reading streak"},
```

Add a line to `HELP_TEXT` under "Daily delivery":

```
/streak - see your current and longest streak
```

---

### `db.py` import additions in `commands.py`

```python
from db import add_subscriber, get_streak, get_subscriber, remove_subscriber, set_delivery_hour
```

---

### `telegram_client.py`

```python
ALLOWED_WEBHOOK_UPDATES = ["message", "edited_message", "message_reaction"]
```

No other changes to this file — `set_webhook`'s payload already uses `ALLOWED_WEBHOOK_UPDATES`, so this takes effect the next time `register_bot_webhook` runs (every startup).

Note: for private (1:1) chats, Telegram sends `message_reaction` (not `message_reaction_count`, which is the anonymized aggregate used for channels) — this is the correct update type to subscribe to here.

---

### `bot_app.py`

New helper to extract a reacting chat ID:

```python
def _extract_reaction_chat_id(update: dict[str, Any]) -> int | None:
    reaction = update.get("message_reaction")
    if not reaction:
        return None
    chat = reaction.get("chat") or {}
    return chat.get("id")
```

In the webhook handler, record activity for both reactions and messages. Reactions short-circuit before command routing (they carry no text):

```python
from db import record_activity
from plan_reader import get_eat_today

...

update_id = update.get("update_id")

reaction_chat_id = _extract_reaction_chat_id(update)
if reaction_chat_id is not None:
    record_activity(str(reaction_chat_id), get_eat_today().isoformat())
    log_event("webhook_reaction", update_id=update_id, chat_id=reaction_chat_id)
    return JSONResponse({"ok": True})

message = _extract_message(update)
if not message:
    log_event("webhook_ignored", reason="no_message", update_id=update_id)
    return JSONResponse({"ok": True})

chat = message.get("chat") or {}
chat_id = chat.get("id")
text = (message.get("text") or "").strip()
if chat_id is not None:
    record_activity(str(chat_id), get_eat_today().isoformat())

if chat_id is None or not text:
    log_event("webhook_ignored", reason="empty_chat_or_text", update_id=update_id, chat_id=chat_id)
    return JSONResponse({"ok": True})
```

Activity is recorded for *any* message with a `chat_id`, including non-text messages (stickers, photos) — consistent with "any interaction counts" (Design Decisions). Only the existing command-routing logic below this block still requires non-empty `text`.

---

## New File: `nudge_check.py`

Hourly cron entrypoint, structured like `daily_bread.py`.

```python
#!/usr/bin/env python3
"""Hourly cron entrypoint: nudge subscribers who haven't interacted today.

Reuses the existing hourly cron trigger. For each subscriber whose
(hour_eat + NUDGE_DELAY_HOURS) % 24 matches the current EAT hour, and who
has no activity logged today and hasn't already been nudged today, send one
gentle reminder.
"""

from __future__ import annotations

from config import NUDGE_DELAY_HOURS
from db import get_subscribers_for_nudge, record_nudge
from logutil import log_event
from plan_reader import get_eat_now, get_eat_today
from telegram_client import send_messages

NUDGE_MESSAGE = (
    "👋 Haven't seen you yet today — your reading's still there whenever "
    "you're ready. No pressure, just a nudge. 🙏"
)


def main() -> None:
    hour = get_eat_now().hour
    today = get_eat_today().isoformat()

    subscribers = get_subscribers_for_nudge(
        current_hour=hour,
        delay_hours=NUDGE_DELAY_HOURS,
        activity_date=today,
        nudge_date=today,
    )
    if not subscribers:
        log_event("nudge_none_due", hour=hour)
        return

    sent = 0
    for sub in subscribers:
        chat_id = sub["chat_id"]
        if send_messages(chat_id, NUDGE_MESSAGE):
            record_nudge(chat_id, today)
            sent += 1

    log_event("nudge_sent", sent=sent, total=len(subscribers), hour=hour)


if __name__ == "__main__":
    main()
```

---

### `run_daily_docker.sh`

Add the nudge check right after the existing daily push — both run on the same hourly cron tick, no new cron entry needed:

```bash
docker compose exec -T bot python daily_bread.py
docker compose exec -T bot python nudge_check.py
```

---

## Startup Sequence (updated)

1. Container starts → `lifespan()` runs
2. `init_db()` creates schema (now includes `activity` and `nudges`, no-op if already exists)
3. Subscribers seeded from env if table was empty (unchanged)
4. `register_bot_webhook` re-registers with `ALLOWED_WEBHOOK_UPDATES` including `message_reaction` — Telegram starts sending reaction updates from this point on
5. At each top-of-hour: cron fires → `daily_bread.py` sends readings + reflection prompts → `nudge_check.py` sends nudges to anyone silent so far today

---

## Migration Path

1. Deploy new code — `activity`/`nudges` tables are created automatically on next container start via `init_db()`
2. Restart the container so `setWebhook` re-registers with `message_reaction` in `allowed_updates`
3. Verify reactions are being received: react to any bot message from a test account, then check `docker compose exec -T bot python -c "import sqlite3,os; print(sqlite3.connect(os.getenv('DB_PATH','/data/bible.db')).execute('SELECT * FROM activity ORDER BY activity_date DESC LIMIT 5').fetchall())"`
4. Update `deploy/run_daily_docker.sh` on the VPS (or redeploy via the existing GitHub Actions flow) to add the `nudge_check.py` line
5. No cron schedule change — same `0 * * * *` entry now runs both scripts

---

## Testing Approach

Follows the existing patterns: `db.py` tests run against a temp file DB via `DB_PATH` monkeypatch (`tests/test_db.py`); dispatch-logic tests monkeypatch the current-hour and send functions (`tests/test_daily_bread.py`).

**`tests/test_db.py` additions:**
- `record_activity` then `has_activity` returns True for that date, False for a different date
- `record_activity` called twice same day is idempotent (no error, single row)
- `get_streak` with no activity rows → `(0, 0, 0)`
- `get_streak` with activity today only → current=1, longest=1, total=1
- `get_streak` with a gap (e.g. activity 3 days ago, nothing since) → current=0, longest=1
- `get_streak` with 5 consecutive days ending yesterday, `today` passed as today → current=5 (grace day)
- `get_streak` longest streak differs from current streak (e.g. a broken earlier run longer than the active one)
- `get_subscribers_for_nudge` matches on `(hour_eat + delay_hours) % 24`, including the hour-wraparound case (e.g. `hour_eat=20, delay_hours=8` → nudge hour `4`)
- `get_subscribers_for_nudge` excludes a subscriber with an activity row for `activity_date`
- `get_subscribers_for_nudge` excludes a subscriber with a nudges row for `nudge_date`

**`tests/test_commands.py` additions:**
- `handle_streak` for a non-subscriber returns the "not subscribed" message
- `handle_streak` for a subscriber with activity returns current/longest/total in the reply text
- `_reading_for_date` output includes a reflection line (via `build_reflection_message`) before the footer

**New `tests/test_nudge_check.py`** (mirrors `tests/test_daily_bread.py`):
- `main()` sends to subscribers returned by `get_subscribers_for_nudge` and calls `record_nudge` for each successful send
- `main()` does nothing (no send, no log of `nudge_sent`) when `get_subscribers_for_nudge` returns `[]`
- A failed `send_messages` does not call `record_nudge` (so a failed nudge can retry next hour, not silently swallowed for the rest of the day)

---

## Dependencies

No new packages. Same as the previous spec — `sqlite3`, `datetime`, `zoneinfo` are stdlib.

---

## Files Changed Summary

| File | Change type |
|---|---|
| `prompts.py` | New |
| `nudge_check.py` | New |
| `db.py` | Add `activity`/`nudges` tables to `init_db()`; add `record_activity`, `has_activity`, `get_streak`, `record_nudge`, `get_subscribers_for_nudge` |
| `config.py` | Add `NUDGE_DELAY_HOURS` |
| `formatting.py` | Add `build_reflection_message()` |
| `daily_bread.py` | Insert reflection message before footer |
| `commands.py` | Insert reflection message in `_reading_for_date`; add `handle_streak` + `/streak` registration |
| `telegram_client.py` | Add `message_reaction` to `ALLOWED_WEBHOOK_UPDATES` |
| `bot_app.py` | Record activity for messages and reactions; handle `message_reaction` updates |
| `run_daily_docker.sh` | Add `nudge_check.py` call after `daily_bread.py` |
| `tests/test_db.py` | Add activity/streak/nudge-eligibility tests |
| `tests/test_commands.py` | Add `handle_streak` tests; reflection-insertion test |
| `tests/test_nudge_check.py` | New |
