# Devotional Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the daily push into a devotional companion — a reflection prompt with every reading, a real streak based on subscriber interaction (not just delivery), a `/streak` command, and one gentle nudge for subscribers who haven't engaged yet that day.

**Architecture:** Two new SQLite tables (`activity`, `nudges`) track engagement and prevent double-nudging. A static prompt bank (`prompts.py`) picks a deterministic daily reflection question with no new API dependency. The webhook handler in `bot_app.py` logs activity for any inbound message or reaction. A new hourly cron entrypoint (`nudge_check.py`) runs alongside the existing `daily_bread.py` to nudge silent subscribers.

**Tech Stack:** Python 3.12, SQLite (stdlib `sqlite3`), `zoneinfo`/`datetime` (stdlib), FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-09-18-devotional-companion-design.md`

## Global Constraints

- Python 3.12; all new code must be compatible (production Docker image is `python:3.12-slim-bookworm`)
- No new runtime dependencies — everything here is stdlib (`sqlite3`, `datetime`, `zoneinfo`)
- `pytest` is already a dev dependency (`requirements-dev.txt`) — no new packages needed
- **Never install packages globally.** All `pip`/`pytest` commands must use the project venv: `./venv/bin/pip` and `./venv/bin/pytest`
- All dates/times are Africa/Nairobi (EAT, UTC+3) — no per-user timezone support
- `chat_id` is stored and passed as `str` throughout, consistent with `subscribers.chat_id`
- All Telegram message content uses HTML parse mode (existing convention); user-facing text must go through `html.escape()`
- `activity_date` and `nudge_date` are `"YYYY-MM-DD"` ISO date strings (EAT calendar date)
- `NUDGE_DELAY_HOURS = 8`, fixed for every subscriber — not configurable per user
- "Any interaction counts" toward a streak — any command, free-text reply, or reaction on a given EAT day marks that day complete. No correlation to a specific message.
- No journaling: reflection prompts are one-way. Replies are not captured or stored beyond marking the day active.
- Reflection prompts come from the static bank in `prompts.py` only — no LLM or external API call for prompt content.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db.py` | Modify | Add `activity`/`nudges` tables; activity, streak, and nudge-eligibility functions |
| `prompts.py` | Create | Static reflection prompt bank + deterministic day-based selection |
| `formatting.py` | Modify | Add `build_reflection_message()` |
| `daily_bread.py` | Modify | Insert reflection message into the daily push |
| `commands.py` | Modify | Insert reflection message into `_reading_for_date`; add `/streak` command |
| `telegram_client.py` | Modify | Add `message_reaction` to `ALLOWED_WEBHOOK_UPDATES` |
| `bot_app.py` | Modify | Record activity for messages and reactions in the webhook handler |
| `config.py` | Modify | Add `NUDGE_DELAY_HOURS` |
| `nudge_check.py` | Create | Hourly cron entrypoint sending gentle nudges |
| `run_daily_docker.sh` | Modify | Run `nudge_check.py` alongside `daily_bread.py` |
| `tests/test_db.py` | Modify | Activity/streak/nudge-eligibility tests |
| `tests/test_prompts.py` | Create | Prompt bank tests |
| `tests/test_formatting.py` | Create | `build_reflection_message` tests |
| `tests/test_daily_bread.py` | Modify | Reflection-message-ordering test |
| `tests/test_commands.py` | Modify | Reflection-insertion test; `/streak` tests |
| `tests/test_bot_app.py` | Create | `_extract_reaction_chat_id` tests |
| `tests/test_nudge_check.py` | Create | Nudge dispatch logic tests |

---

## Task 1: Activity tracking & streak computation

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py` (append)

**Interfaces:**
- Consumes: existing `_connect()` in `db.py`
- Produces:
  - `record_activity(chat_id: str, activity_date: str) -> None`
  - `has_activity(chat_id: str, activity_date: str) -> bool`
  - `get_streak(chat_id: str, today: date) -> tuple[int, int, int]` — `(current_streak, longest_streak, total_days_active)`

- [ ] **Step 1: Write failing tests**

Append to the end of `tests/test_db.py`:

```python
# --- activity tracking & streaks ---

def test_record_activity_then_has_activity_true():
    from db import record_activity, has_activity
    record_activity("111", "2026-09-18")
    assert has_activity("111", "2026-09-18") is True


def test_has_activity_false_for_different_date():
    from db import record_activity, has_activity
    record_activity("111", "2026-09-18")
    assert has_activity("111", "2026-09-19") is False


def test_has_activity_false_when_no_rows():
    from db import has_activity
    assert has_activity("999", "2026-09-18") is False


def test_record_activity_twice_same_day_is_idempotent():
    from db import record_activity, has_activity
    record_activity("111", "2026-09-18")
    record_activity("111", "2026-09-18")  # must not raise
    assert has_activity("111", "2026-09-18") is True


def test_get_streak_no_activity_returns_zeros():
    from db import get_streak
    from datetime import date
    assert get_streak("111", date(2026, 9, 18)) == (0, 0, 0)


def test_get_streak_activity_today_only():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-18")
    assert get_streak("111", date(2026, 9, 18)) == (1, 1, 1)


def test_get_streak_consecutive_days_ending_today():
    from db import record_activity, get_streak
    from datetime import date
    for day in ("2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"):
        record_activity("111", day)
    assert get_streak("111", date(2026, 9, 18)) == (5, 5, 5)


def test_get_streak_grace_day_when_last_activity_was_yesterday():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-17")
    current, longest, total = get_streak("111", date(2026, 9, 18))
    assert current == 1
    assert longest == 1
    assert total == 1


def test_get_streak_broken_when_gap_before_yesterday():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-14")
    current, longest, total = get_streak("111", date(2026, 9, 18))
    assert current == 0
    assert longest == 1
    assert total == 1


def test_get_streak_longest_can_exceed_current():
    from db import record_activity, get_streak
    from datetime import date
    # A broken 4-day run, then a fresh 1-day run today
    for day in ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"):
        record_activity("111", day)
    record_activity("111", "2026-09-18")
    current, longest, total = get_streak("111", date(2026, 9, 18))
    assert current == 1
    assert longest == 4
    assert total == 5


def test_get_streak_only_counts_this_chat_id():
    from db import record_activity, get_streak
    from datetime import date
    record_activity("111", "2026-09-18")
    record_activity("222", "2026-09-18")
    record_activity("222", "2026-09-17")
    assert get_streak("111", date(2026, 9, 18)) == (1, 1, 1)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
./venv/bin/pytest tests/test_db.py -v -k "activity or streak"
```

Expected: `ImportError` / `AttributeError` — `record_activity`, `has_activity`, `get_streak` don't exist yet.

- [ ] **Step 3: Update the import line in `db.py`**

Find:
```python
from datetime import datetime, timezone
```

Replace with:
```python
from datetime import date, datetime, timedelta, timezone
```

- [ ] **Step 4: Add the `activity` table to `init_db()`**

Find (inside `init_db()`):
```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id    TEXT    PRIMARY KEY,
                hour_eat   INTEGER NOT NULL DEFAULT 6,
                joined_at  TEXT    NOT NULL,
                source     TEXT    NOT NULL DEFAULT 'command'
            )
        """)
        conn.commit()
```

Replace with:
```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id    TEXT    PRIMARY KEY,
                hour_eat   INTEGER NOT NULL DEFAULT 6,
                joined_at  TEXT    NOT NULL,
                source     TEXT    NOT NULL DEFAULT 'command'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                chat_id        TEXT    NOT NULL,
                activity_date  TEXT    NOT NULL,
                first_seen_at  TEXT    NOT NULL,
                PRIMARY KEY (chat_id, activity_date)
            )
        """)
        conn.commit()
```

- [ ] **Step 5: Append `record_activity`, `has_activity`, `get_streak` to the end of `db.py`**

```python
def record_activity(chat_id: str, activity_date: str) -> None:
    """Log an interaction for chat_id on activity_date (YYYY-MM-DD). Idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO activity (chat_id, activity_date, first_seen_at)"
            " VALUES (?, ?, ?)",
            (chat_id, activity_date, now),
        )
        conn.commit()
    finally:
        conn.close()


def has_activity(chat_id: str, activity_date: str) -> bool:
    """True if chat_id has an activity row for activity_date."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM activity WHERE chat_id = ? AND activity_date = ?",
            (chat_id, activity_date),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_streak(chat_id: str, today: date) -> tuple[int, int, int]:
    """
    Return (current_streak, longest_streak, total_days_active) for chat_id.

    current_streak is 0 if the most recent activity date isn't today or
    yesterday relative to `today`.
    """
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

- [ ] **Step 6: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_db.py -v
```

Expected: all tests PASS (existing subscriber tests plus the 11 new ones).

- [ ] **Step 7: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add activity tracking and streak computation"
```

---

## Task 2: Nudge eligibility persistence

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py` (append)

**Interfaces:**
- Consumes: `activity` table and `_connect()` from Task 1
- Produces:
  - `record_nudge(chat_id: str, nudge_date: str) -> None`
  - `get_subscribers_for_nudge(*, current_hour: int, delay_hours: int, activity_date: str, nudge_date: str) -> list[dict[str, Any]]` — each dict has `chat_id` and `hour_eat`

- [ ] **Step 1: Write failing tests**

Append to the end of `tests/test_db.py`:

```python
# --- nudge eligibility ---

def test_get_subscribers_for_nudge_matches_hour():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert [r["chat_id"] for r in result] == ["111"]


def test_get_subscribers_for_nudge_wraps_past_midnight():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=20)
    result = get_subscribers_for_nudge(
        current_hour=4, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert [r["chat_id"] for r in result] == ["111"]


def test_get_subscribers_for_nudge_excludes_non_matching_hour():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    result = get_subscribers_for_nudge(
        current_hour=9, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result == []


def test_get_subscribers_for_nudge_excludes_active_subscriber():
    from db import add_subscriber, record_activity, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-18")
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result == []


def test_get_subscribers_for_nudge_excludes_already_nudged():
    from db import add_subscriber, record_nudge, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    record_nudge("111", "2026-09-18")
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result == []


def test_get_subscribers_for_nudge_returns_hour_eat():
    from db import add_subscriber, get_subscribers_for_nudge
    add_subscriber("111", hour_eat=6)
    result = get_subscribers_for_nudge(
        current_hour=14, delay_hours=8, activity_date="2026-09-18", nudge_date="2026-09-18"
    )
    assert result[0]["hour_eat"] == 6


def test_record_nudge_is_idempotent():
    from db import record_nudge
    record_nudge("111", "2026-09-18")
    record_nudge("111", "2026-09-18")  # must not raise
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
./venv/bin/pytest tests/test_db.py -v -k "nudge"
```

Expected: `ImportError` / `AttributeError` — `record_nudge`, `get_subscribers_for_nudge` don't exist yet.

- [ ] **Step 3: Add the `nudges` table to `init_db()`**

Find (the `activity` table statement added in Task 1):
```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                chat_id        TEXT    NOT NULL,
                activity_date  TEXT    NOT NULL,
                first_seen_at  TEXT    NOT NULL,
                PRIMARY KEY (chat_id, activity_date)
            )
        """)
        conn.commit()
```

Replace with:
```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                chat_id        TEXT    NOT NULL,
                activity_date  TEXT    NOT NULL,
                first_seen_at  TEXT    NOT NULL,
                PRIMARY KEY (chat_id, activity_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nudges (
                chat_id     TEXT    NOT NULL,
                nudge_date  TEXT    NOT NULL,
                sent_at     TEXT    NOT NULL,
                PRIMARY KEY (chat_id, nudge_date)
            )
        """)
        conn.commit()
```

- [ ] **Step 4: Append `record_nudge` and `get_subscribers_for_nudge` to the end of `db.py`**

```python
def record_nudge(chat_id: str, nudge_date: str) -> None:
    """Log that a nudge was sent to chat_id on nudge_date. Idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO nudges (chat_id, nudge_date, sent_at) VALUES (?, ?, ?)",
            (chat_id, nudge_date, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_subscribers_for_nudge(
    *, current_hour: int, delay_hours: int, activity_date: str, nudge_date: str
) -> list[dict[str, Any]]:
    """
    Return subscriber rows {chat_id, hour_eat} where:
      (hour_eat + delay_hours) % 24 == current_hour
      AND no activity row for activity_date
      AND no nudges row for nudge_date
    """
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

- [ ] **Step 5: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_db.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add nudge eligibility persistence"
```

---

## Task 3: Reflection prompt content & formatting

**Files:**
- Create: `prompts.py`
- Modify: `formatting.py`
- Test: `tests/test_prompts.py` (create)
- Test: `tests/test_formatting.py` (create)

**Interfaces:**
- Produces:
  - `REFLECTION_PROMPTS: list[str]` in `prompts.py`
  - `prompt_for_date(day: date) -> str` in `prompts.py`
  - `build_reflection_message(prompt: str) -> str` in `formatting.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_prompts.py`:

```python
"""Tests for prompts.py reflection prompt bank."""

from __future__ import annotations

from datetime import date, timedelta


def test_prompt_for_date_returns_a_bank_entry():
    from prompts import REFLECTION_PROMPTS, prompt_for_date
    result = prompt_for_date(date(2026, 9, 18))
    assert result in REFLECTION_PROMPTS


def test_prompt_for_date_is_deterministic():
    from prompts import prompt_for_date
    d = date(2026, 9, 18)
    assert prompt_for_date(d) == prompt_for_date(d)


def test_prompt_for_date_varies_by_day_of_year():
    from prompts import prompt_for_date
    assert prompt_for_date(date(2026, 1, 1)) != prompt_for_date(date(2026, 1, 2))


def test_prompt_bank_has_at_least_40_entries():
    from prompts import REFLECTION_PROMPTS
    assert len(REFLECTION_PROMPTS) >= 40


def test_prompt_for_date_wraps_around_bank_length():
    from prompts import REFLECTION_PROMPTS, prompt_for_date
    bank_len = len(REFLECTION_PROMPTS)
    d1 = date(2026, 1, 1)
    d2 = d1 + timedelta(days=bank_len)
    assert prompt_for_date(d1) == prompt_for_date(d2)
```

Create `tests/test_formatting.py`:

```python
"""Tests for formatting.py message builders."""

from __future__ import annotations


def test_build_reflection_message_includes_prompt_text():
    from formatting import build_reflection_message
    msg = build_reflection_message("What stood out to you today?")
    assert "What stood out to you today?" in msg


def test_build_reflection_message_escapes_html():
    from formatting import build_reflection_message
    msg = build_reflection_message("Is <b>this</b> safe?")
    assert "<b>this</b>" not in msg
    assert "&lt;b&gt;this&lt;/b&gt;" in msg


def test_build_reflection_message_has_reflect_label():
    from formatting import build_reflection_message
    msg = build_reflection_message("A prompt")
    assert "Reflect" in msg
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
./venv/bin/pytest tests/test_prompts.py tests/test_formatting.py -v
```

Expected: `ModuleNotFoundError: No module named 'prompts'` and `ImportError: cannot import name 'build_reflection_message'`.

- [ ] **Step 3: Create `prompts.py`**

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

- [ ] **Step 4: Add `build_reflection_message` to the end of `formatting.py`**

```python
def build_reflection_message(prompt: str) -> str:
    return f"🤔 <b>Reflect</b>\n{html.escape(prompt)}"
```

- [ ] **Step 5: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_prompts.py tests/test_formatting.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add prompts.py formatting.py tests/test_prompts.py tests/test_formatting.py
git commit -m "feat: add reflection prompt bank and message formatting"
```

---

## Task 4: Daily push includes reflection prompt

**Files:**
- Modify: `daily_bread.py`
- Test: `tests/test_daily_bread.py` (append)

**Interfaces:**
- Consumes:
  - `prompt_for_date(day: date) -> str` from `prompts.py` (Task 3)
  - `build_reflection_message(prompt: str) -> str` from `formatting.py` (Task 3)
- Produces: the daily push's `messages` list now has the reflection message inserted immediately before the footer (`messages[-1]` stays the footer)

- [ ] **Step 1: Write failing test**

Append to the end of `tests/test_daily_bread.py`:

```python
def test_main_includes_reflection_message_before_footer(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    sent_messages = []

    def mock_send(chat_id, messages, **kwargs):
        sent_messages.extend(messages)
        return True

    monkeypatch.setattr("daily_bread.send_messages", mock_send)
    monkeypatch.setattr(
        "daily_bread.get_reference_for_today",
        lambda today: (1, "Monday", "Gen 1"),
    )
    monkeypatch.setattr(
        "daily_bread.fetch_bible_text",
        lambda ref: ("Gen 1", [("1", "In the beginning God created...")]),
    )
    monkeypatch.setattr(
        "daily_bread.build_reading_messages",
        lambda *a, **kw: ["reading message", "footer"],
    )
    monkeypatch.setattr("daily_bread.prompt_for_date", lambda day: "Test prompt?")

    import daily_bread
    daily_bread.main()

    assert sent_messages[-1] == "footer"
    assert "Test prompt?" in sent_messages[-2]
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
./venv/bin/pytest tests/test_daily_bread.py -v -k reflection
```

Expected: FAIL — `sent_messages` is `["reading message", "footer"]`, no reflection text present (or `AttributeError` since `daily_bread.prompt_for_date` doesn't exist yet).

- [ ] **Step 3: Update `daily_bread.py`**

Find the import block:
```python
from bible_client import fetch_bible_text
from config import TIMEZONE
from db import get_subscribers_for_hour
from formatting import build_reading_messages
from logutil import log_event
from plan_reader import get_eat_today, get_reference_for_today
from telegram_client import send_messages
```

Replace with:
```python
from bible_client import fetch_bible_text
from config import TIMEZONE
from db import get_subscribers_for_hour
from formatting import build_reading_messages, build_reflection_message
from logutil import log_event
from plan_reader import get_eat_today, get_reference_for_today
from prompts import prompt_for_date
from telegram_client import send_messages
```

Find:
```python
    messages = build_reading_messages(plan_week, day_name, returned_ref, chapters)

    sent = 0
```

Replace with:
```python
    messages = build_reading_messages(plan_week, day_name, returned_ref, chapters)
    messages.insert(-1, build_reflection_message(prompt_for_date(today)))

    sent = 0
```

- [ ] **Step 4: Run test — confirm it passes**

```bash
./venv/bin/pytest tests/test_daily_bread.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
./venv/bin/pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add daily_bread.py tests/test_daily_bread.py
git commit -m "feat: include reflection prompt in daily push"
```

---

## Task 5: On-demand reading commands include reflection prompt

**Files:**
- Modify: `commands.py`
- Test: `tests/test_commands.py` (append)

**Interfaces:**
- Consumes:
  - `prompt_for_date(day: date) -> str` from `prompts.py` (Task 3)
  - `build_reflection_message(prompt: str) -> str` from `formatting.py` (Task 3)
- Produces: `_reading_for_date()` output now has the reflection message inserted immediately before the footer — same contract as Task 4, so `/today` and `/day` match the daily push

- [ ] **Step 1: Write failing test**

Append to the end of `tests/test_commands.py`:

```python
def test_handle_today_includes_reflection_prompt(monkeypatch):
    import commands
    from formatting import FOOTER

    monkeypatch.setattr(commands, "get_reference_for_date", lambda day: (1, "Monday", "Gen 1"))
    monkeypatch.setattr(
        commands, "fetch_bible_text", lambda ref: ("Gen 1", [("1", "In the beginning...")])
    )
    monkeypatch.setattr(commands, "prompt_for_date", lambda day: "Test reflection prompt?")

    from commands import handle_today
    msgs = handle_today("", chat_id="42")

    assert "Test reflection prompt?" in msgs[-2]
    assert msgs[-1] == FOOTER
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
./venv/bin/pytest tests/test_commands.py -v -k reflection
```

Expected: FAIL — `AttributeError: <module 'commands'> does not have the attribute 'prompt_for_date'`.

- [ ] **Step 3: Update `commands.py`**

Find the import block:
```python
from bible_client import (
    chapter_span_too_large,
    fetch_bible_text,
    fetch_verse_reference,
    parse_reference,
)
from config import MAX_CHAPTERS_PER_REQUEST
from db import add_subscriber, get_subscriber, remove_subscriber, set_delivery_hour
from formatting import (
    build_passage_messages,
    build_reading_messages,
    build_verse_messages,
)
from plan_reader import get_eat_now, get_eat_today, get_reference_for_date
```

Replace with:
```python
from bible_client import (
    chapter_span_too_large,
    fetch_bible_text,
    fetch_verse_reference,
    parse_reference,
)
from config import MAX_CHAPTERS_PER_REQUEST
from db import add_subscriber, get_subscriber, remove_subscriber, set_delivery_hour
from formatting import (
    build_passage_messages,
    build_reading_messages,
    build_reflection_message,
    build_verse_messages,
)
from plan_reader import get_eat_now, get_eat_today, get_reference_for_date
from prompts import prompt_for_date
```

Find `_reading_for_date`:
```python
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
    return build_reading_messages(
        plan_week,
        day_name,
        returned_ref,
        chapters,
        date_label=date_label,
    )
```

Replace with:
```python
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
```

- [ ] **Step 4: Run test — confirm it passes**

```bash
./venv/bin/pytest tests/test_commands.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
./venv/bin/pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add commands.py tests/test_commands.py
git commit -m "feat: include reflection prompt in /today and /day"
```

---

## Task 6: `/streak` command

**Files:**
- Modify: `commands.py`
- Test: `tests/test_commands.py` (append)

**Interfaces:**
- Consumes:
  - `get_streak(chat_id: str, today: date) -> tuple[int, int, int]` from `db.py` (Task 1)
  - `get_subscriber(chat_id: str) -> dict | None` from `db.py` (already imported)
  - `get_eat_today() -> date` from `plan_reader` (already imported)
- Produces: `handle_streak(args: str, chat_id: str = "") -> list[str]`, registered as `/streak`

- [ ] **Step 1: Write failing tests**

Append to the end of `tests/test_commands.py`:

```python
def test_handle_streak_not_subscribed():
    from commands import handle_streak
    msgs = handle_streak("", chat_id="42")
    assert "not subscribed" in msgs[0].lower()


def test_handle_streak_shows_current_and_longest(monkeypatch):
    from commands import handle_subscribe, handle_streak
    from db import record_activity
    from datetime import date
    import commands

    handle_subscribe("", chat_id="42")
    record_activity("42", "2026-09-17")
    record_activity("42", "2026-09-18")
    monkeypatch.setattr(commands, "get_eat_today", lambda: date(2026, 9, 18))

    msgs = handle_streak("", chat_id="42")
    assert "Current: 2 days" in msgs[0]
    assert "Longest: 2 days" in msgs[0]
    assert "Total days active: 2" in msgs[0]


def test_handle_streak_singular_day_wording(monkeypatch):
    from commands import handle_subscribe, handle_streak
    from db import record_activity
    from datetime import date
    import commands

    handle_subscribe("", chat_id="42")
    record_activity("42", "2026-09-18")
    monkeypatch.setattr(commands, "get_eat_today", lambda: date(2026, 9, 18))

    msgs = handle_streak("", chat_id="42")
    assert "Current: 1 day\n" in msgs[0]


def test_handle_message_text_routes_streak():
    from commands import handle_message_text, handle_subscribe
    handle_subscribe("", chat_id="42")
    msgs = handle_message_text("/streak", chat_id="42")
    assert msgs is not None
    assert "streak" in msgs[0].lower()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
./venv/bin/pytest tests/test_commands.py -v -k streak
```

Expected: `ImportError: cannot import name 'handle_streak'`.

- [ ] **Step 3: Update the `db` import line in `commands.py`**

Find:
```python
from db import add_subscriber, get_subscriber, remove_subscriber, set_delivery_hour
```

Replace with:
```python
from db import add_subscriber, get_streak, get_subscriber, remove_subscriber, set_delivery_hour
```

- [ ] **Step 4: Add `handle_streak` after `handle_settime`**

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

- [ ] **Step 5: Register the command**

Find `BOT_COMMANDS`:
```python
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
]
```

Replace with:
```python
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
```

Find `HANDLERS`:
```python
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
}
```

Replace with:
```python
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
```

Find, in `HELP_TEXT`:
```
/settime 9 - change your delivery hour
/unsubscribe - stop daily readings
```

Replace with:
```
/settime 9 - change your delivery hour
/unsubscribe - stop daily readings
/streak - see your current and longest streak
```

- [ ] **Step 6: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_commands.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Run full test suite**

```bash
./venv/bin/pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add commands.py tests/test_commands.py
git commit -m "feat: add /streak command"
```

---

## Task 7: Webhook records activity for messages and reactions

**Files:**
- Modify: `telegram_client.py`
- Modify: `bot_app.py`
- Test: `tests/test_bot_app.py` (create)

**Interfaces:**
- Consumes:
  - `record_activity(chat_id: str, activity_date: str) -> None` from `db.py` (Task 1)
  - `get_eat_today() -> date` from `plan_reader`
- Produces: `_extract_reaction_chat_id(update: dict[str, Any]) -> int | None` in `bot_app.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_bot_app.py`:

```python
"""Tests for bot_app.py webhook helpers."""

from __future__ import annotations


def test_extract_reaction_chat_id_present():
    from bot_app import _extract_reaction_chat_id
    update = {
        "message_reaction": {
            "chat": {"id": 555},
            "message_id": 10,
            "date": 1234567890,
            "old_reaction": [],
            "new_reaction": [{"type": "emoji", "emoji": "🙏"}],
        }
    }
    assert _extract_reaction_chat_id(update) == 555


def test_extract_reaction_chat_id_absent():
    from bot_app import _extract_reaction_chat_id
    assert _extract_reaction_chat_id({"message": {}}) is None


def test_extract_reaction_chat_id_missing_chat():
    from bot_app import _extract_reaction_chat_id
    assert _extract_reaction_chat_id({"message_reaction": {}}) is None
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
./venv/bin/pytest tests/test_bot_app.py -v
```

Expected: `ImportError: cannot import name '_extract_reaction_chat_id'`.

- [ ] **Step 3: Update `ALLOWED_WEBHOOK_UPDATES` in `telegram_client.py`**

Find:
```python
ALLOWED_WEBHOOK_UPDATES = ["message", "edited_message"]
```

Replace with:
```python
ALLOWED_WEBHOOK_UPDATES = ["message", "edited_message", "message_reaction"]
```

- [ ] **Step 4: Update imports in `bot_app.py`**

Find:
```python
from commands import BOT_COMMANDS, handle_message_text
from config import (
    get_app_host,
    get_app_port,
    get_bot_token,
    get_webhook_secret,
    get_webhook_url,
    is_placeholder_token,
)
from logutil import log_event
from telegram_client import (
    register_bot_webhook,
    send_messages,
    set_my_commands,
)
```

Replace with:
```python
from commands import BOT_COMMANDS, handle_message_text
from config import (
    get_app_host,
    get_app_port,
    get_bot_token,
    get_webhook_secret,
    get_webhook_url,
    is_placeholder_token,
)
from db import record_activity
from logutil import log_event
from plan_reader import get_eat_today
from telegram_client import (
    register_bot_webhook,
    send_messages,
    set_my_commands,
)
```

- [ ] **Step 5: Add `_extract_reaction_chat_id` after `_extract_message`**

Find:
```python
def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("edited_message")
```

Replace with:
```python
def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("edited_message")


def _extract_reaction_chat_id(update: dict[str, Any]) -> int | None:
    reaction = update.get("message_reaction")
    if not reaction:
        return None
    chat = reaction.get("chat") or {}
    return chat.get("id")
```

- [ ] **Step 6: Record activity in the webhook handler**

Find:
```python
    update_id = update.get("update_id")
    message = _extract_message(update)
    if not message:
        log_event("webhook_ignored", reason="no_message", update_id=update_id)
        return JSONResponse({"ok": True})

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None or not text:
        log_event(
            "webhook_ignored",
            reason="empty_chat_or_text",
            update_id=update_id,
            chat_id=chat_id,
        )
        return JSONResponse({"ok": True})
```

Replace with:
```python
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
        log_event(
            "webhook_ignored",
            reason="empty_chat_or_text",
            update_id=update_id,
            chat_id=chat_id,
        )
        return JSONResponse({"ok": True})
```

- [ ] **Step 7: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_bot_app.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Run full test suite**

```bash
./venv/bin/pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 9: Commit**

```bash
git add telegram_client.py bot_app.py tests/test_bot_app.py
git commit -m "feat: record subscriber activity from messages and reactions"
```

---

## Task 8: Nudge cron entrypoint

**Files:**
- Modify: `config.py`
- Create: `nudge_check.py`
- Test: `tests/test_nudge_check.py` (create)

**Interfaces:**
- Consumes:
  - `get_subscribers_for_nudge(*, current_hour, delay_hours, activity_date, nudge_date) -> list[dict[str, Any]]` from `db.py` (Task 2)
  - `record_nudge(chat_id: str, nudge_date: str) -> None` from `db.py` (Task 2)
  - `send_messages(chat_id, messages) -> bool` from `telegram_client.py`
  - `get_eat_now() -> datetime`, `get_eat_today() -> date` from `plan_reader`
  - `NUDGE_DELAY_HOURS` from `config.py`
- Produces: `main() -> None` in `nudge_check.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_nudge_check.py`:

```python
"""Tests for nudge_check.py dispatch logic."""

from __future__ import annotations

from datetime import date, datetime

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


FIXED_NOW = datetime(2026, 9, 18, 14, 0, 0)
FIXED_TODAY = date(2026, 9, 18)


def test_main_does_nothing_when_none_due(monkeypatch):
    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    import nudge_check
    nudge_check.main()  # must not raise; no subscribers exist


def test_main_sends_nudge_to_eligible_subscriber(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)  # nudge hour = (6 + 8) % 24 = 14

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )

    import nudge_check
    nudge_check.main()

    assert sent_to == ["111"]


def test_main_does_not_double_nudge_same_day(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )

    import nudge_check
    nudge_check.main()
    nudge_check.main()

    assert sent_to == ["111"]


def test_main_skips_subscriber_with_activity_today(monkeypatch):
    from db import add_subscriber, record_activity
    add_subscriber("111", hour_eat=6)
    record_activity("111", "2026-09-18")

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )

    import nudge_check
    nudge_check.main()

    assert sent_to == []


def test_main_does_not_record_nudge_on_failed_send(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("nudge_check.get_eat_now", lambda: FIXED_NOW)
    monkeypatch.setattr("nudge_check.get_eat_today", lambda: FIXED_TODAY)
    monkeypatch.setattr(
        "nudge_check.send_messages", lambda chat_id, messages, **kwargs: False
    )

    import nudge_check
    nudge_check.main()

    sent_to = []
    monkeypatch.setattr(
        "nudge_check.send_messages",
        lambda chat_id, messages, **kwargs: sent_to.append(str(chat_id)) or True,
    )
    nudge_check.main()

    assert sent_to == ["111"]
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
./venv/bin/pytest tests/test_nudge_check.py -v
```

Expected: `ModuleNotFoundError: No module named 'nudge_check'`.

- [ ] **Step 3: Add `NUDGE_DELAY_HOURS` to `config.py`**

Find:
```python
SEND_DELAY_SEC = 0.35
CACHE_TTL_SEC = 3600

TIMEZONE = "Africa/Nairobi"
```

Replace with:
```python
SEND_DELAY_SEC = 0.35
CACHE_TTL_SEC = 3600
NUDGE_DELAY_HOURS = 8

TIMEZONE = "Africa/Nairobi"
```

- [ ] **Step 4: Create `nudge_check.py`**

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

- [ ] **Step 5: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_nudge_check.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
./venv/bin/pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add config.py nudge_check.py tests/test_nudge_check.py
git commit -m "feat: add hourly nudge cron entrypoint"
```

---

## Task 9: Deployment wiring and VPS verification

This task has no automated tests — it wires the new script into the existing cron trigger and verifies the whole feature end-to-end on the VPS, the same way Task 5 of the subscriber-store plan verified that feature manually.

**Files:**
- Modify: `run_daily_docker.sh`

- [ ] **Step 1: Add the nudge check to `run_daily_docker.sh`**

Find:
```bash
docker compose exec -T bot python daily_bread.py
```

Replace with:
```bash
docker compose exec -T bot python daily_bread.py
docker compose exec -T bot python nudge_check.py
```

- [ ] **Step 2: Commit**

```bash
git add run_daily_docker.sh
git commit -m "feat: run nudge check alongside daily push"
```

- [ ] **Step 3: Deploy and restart (on the VPS)**

```bash
cd ~/opt/bible
git pull
docker compose build --no-cache
docker compose up -d
docker logs bible-bot --tail 30
```

Confirm the startup log shows `webhook_register_result` with `ok: true` — this is the restart that re-registers the webhook with `message_reaction` in `allowed_updates`.

- [ ] **Step 4: Verify the new tables exist**

```bash
docker compose exec -T bot python -c "import sqlite3,os; conn=sqlite3.connect(os.getenv('DB_PATH','/data/bible.db')); print(conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall())"
```

Expected: `[('subscribers',), ('activity',), ('nudges',)]` (order may vary).

- [ ] **Step 5: Verify reflection prompts and `/streak` live**

From a subscribed Telegram account, send `/today`. Expected: the reading, then a `🤔 Reflect` message, then the footer.

Send `/streak`. Expected: current/longest/total streak reply.

- [ ] **Step 6: Verify reaction tracking**

React to any message the bot sent (long-press → pick an emoji, in a private chat). Then check:

```bash
docker compose exec -T bot python -c "import sqlite3,os; conn=sqlite3.connect(os.getenv('DB_PATH','/data/bible.db')); print(conn.execute('SELECT * FROM activity ORDER BY activity_date DESC LIMIT 5').fetchall())"
```

Expected: a row for your `chat_id` with today's date.

- [ ] **Step 7: Confirm no cron schedule change is needed**

```bash
crontab -l | grep bible
```

Expected: the existing `0 * * * *` entry — `run_daily_docker.sh` now runs both `daily_bread.py` and `nudge_check.py` on the same hourly tick, so no crontab edit is required.

---

## Self-Review Checklist

- [x] **Spec coverage:** Data model (Tasks 1–2), reflection prompts (Task 3), daily push + on-demand commands (Tasks 4–5), `/streak` (Task 6), webhook/reaction plumbing (Task 7), nudges (Task 8), deploy/cron wiring (Task 9) — every spec section maps to a task.
- [x] **Placeholder scan:** No TBD/TODO; every step has literal code or an exact shell command; all test assertions are concrete values, not "add appropriate assertions."
- [x] **Type consistency:** `record_activity`/`has_activity`/`record_nudge` take `chat_id: str` and date strings throughout — matches `subscribers.chat_id` (`str`) convention. `get_streak(chat_id: str, today: date) -> tuple[int, int, int]` defined in Task 1, called identically in Task 6's `handle_streak`. `get_subscribers_for_nudge` keyword args (`current_hour`, `delay_hours`, `activity_date`, `nudge_date`) match between its Task 2 definition and Task 8's `nudge_check.py` call site. `prompt_for_date(day: date) -> str` and `build_reflection_message(prompt: str) -> str` (Task 3) are called with matching signatures in Tasks 4 and 5.
- [x] **Insertion contract:** Both Task 4 (`daily_bread.py`) and Task 5 (`commands.py`) use the identical `messages.insert(-1, build_reflection_message(...))` pattern, relying on `build_passage_messages` always appending the footer last — verified against the current `formatting.py` implementation.
