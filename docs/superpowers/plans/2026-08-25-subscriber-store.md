# Subscriber Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `TELEGRAM_CHAT_IDS` env-var recipient list with a SQLite-backed subscriber store that users self-manage via `/subscribe`, `/unsubscribe`, and `/settime` bot commands, with per-subscriber hourly delivery.

**Architecture:** A new `db.py` module owns all SQLite access (one `subscribers` table, stdlib `sqlite3` only). Command handlers in `commands.py` call `db.py` directly. `daily_bread.py` queries the DB for subscribers whose stored hour matches the current EAT hour; the cron entry changes from once-daily to top-of-every-hour so each person's chosen time fires independently.

**Tech Stack:** Python 3.12, SQLite (stdlib `sqlite3`), `zoneinfo` (stdlib), FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-08-25-subscriber-store-design.md`

## Global Constraints

- Python 3.12; all new code must be compatible
- No new runtime dependencies — `sqlite3` and `zoneinfo` are stdlib
- `pytest` is the only new dev dependency; add it to `requirements-dev.txt` (not `requirements.txt`)
- **Never install packages globally.** All `pip` and `pytest` commands must use the project venv: `./venv/bin/pip` and `./venv/bin/pytest`. Do not run bare `pip` or `pytest`.
- Delivery times are always Africa/Nairobi (EAT, UTC+3) — no per-user timezone support
- Valid delivery hours: integers 0–23 inclusive
- Default delivery hour: 6 (6:00 EAT)
- All Telegram message content uses HTML parse mode (existing convention)
- `chat_id` is stored and passed as `str` throughout (Telegram IDs can exceed int32)
- Named Docker volume `bible-data` (not a bind mount) so Docker manages permissions

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db.py` | **Create** | All SQLite subscriber CRUD; no Telegram or config logic |
| `tests/__init__.py` | **Create** | Empty — marks tests as a package |
| `tests/test_db.py` | **Create** | Full unit coverage of `db.py` using temp file DB |
| `requirements-dev.txt` | **Create** | `pytest` only |
| `config.py` | **Modify** | Add `get_db_path()` |
| `commands.py` | **Modify** | Add `/subscribe`, `/unsubscribe`, `/settime`; update handler signatures |
| `tests/test_commands.py` | **Create** | Unit tests for new commands |
| `daily_bread.py` | **Modify** | Query DB by EAT hour; extract testable helpers |
| `telegram_client.py` | **Modify** | Remove `send_to_configured_chats` and `get_chat_ids` import |
| `tests/test_daily_bread.py` | **Create** | Test dispatch selects correct subscribers |
| `bot_app.py` | **Modify** | Init DB in lifespan; pass `chat_id` to `handle_message_text` |
| `docker-compose.yml` | **Modify** | Add named volume `bible-data:/data` |
| `Dockerfile` | **Modify** | Copy `db.py`; create `/data` dir owned by `appuser` |
| `.gitignore` | **Modify** | Add `data/` |
| `.env.example` | **Modify** | Update `TELEGRAM_CHAT_IDS` comment; add `DB_PATH` note |

---

## Task 1: Test infrastructure + DB module

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_db.py`
- Modify: `config.py` (add `get_db_path`)
- Create: `db.py`

**Interfaces:**
- Produces:
  - `get_db_path() -> str` in `config.py`
  - `init_db() -> None` in `db.py`
  - `seed_from_env(chat_ids: list[str], *, default_hour: int = 6) -> int` in `db.py`
  - `add_subscriber(chat_id: str, *, hour_eat: int = 6) -> bool` in `db.py`
  - `remove_subscriber(chat_id: str) -> bool` in `db.py`
  - `set_delivery_hour(chat_id: str, hour_eat: int) -> bool` in `db.py`
  - `get_subscribers_for_hour(hour_eat: int) -> list[str]` in `db.py`
  - `get_subscriber(chat_id: str) -> dict | None` in `db.py`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest==8.3.5
```

- [ ] **Step 2: Create `tests/__init__.py`**

Empty file — just `touch tests/__init__.py`.

- [ ] **Step 3: Add `get_db_path()` to `config.py`**

Add after the `is_placeholder_token` function:

```python
def get_db_path() -> str:
    return os.getenv("DB_PATH", "/data/bible.db").strip() or "/data/bible.db"
```

- [ ] **Step 4: Write failing tests for `db.py`**

Create `tests/test_db.py`:

```python
"""Tests for db.py — all run against a temp file DB via DB_PATH monkeypatch."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


def test_add_subscriber_new():
    from db import add_subscriber
    assert add_subscriber("111") is True


def test_add_subscriber_duplicate_returns_false():
    from db import add_subscriber
    add_subscriber("111")
    assert add_subscriber("111") is False


def test_add_subscriber_default_hour_is_6():
    from db import add_subscriber, get_subscriber
    add_subscriber("111")
    assert get_subscriber("111")["hour_eat"] == 6


def test_add_subscriber_custom_hour():
    from db import add_subscriber, get_subscriber
    add_subscriber("111", hour_eat=9)
    assert get_subscriber("111")["hour_eat"] == 9


def test_add_subscriber_source_is_command():
    from db import add_subscriber, get_subscriber
    add_subscriber("111")
    assert get_subscriber("111")["source"] == "command"


def test_remove_subscriber_exists():
    from db import add_subscriber, remove_subscriber
    add_subscriber("111")
    assert remove_subscriber("111") is True


def test_remove_subscriber_not_found():
    from db import remove_subscriber
    assert remove_subscriber("999") is False


def test_remove_subscriber_then_gone():
    from db import add_subscriber, remove_subscriber, get_subscriber
    add_subscriber("111")
    remove_subscriber("111")
    assert get_subscriber("111") is None


def test_get_subscribers_for_hour_single_match():
    from db import add_subscriber, get_subscribers_for_hour
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=9)
    assert get_subscribers_for_hour(6) == ["111"]


def test_get_subscribers_for_hour_multiple_matches():
    from db import add_subscriber, get_subscribers_for_hour
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=6)
    assert set(get_subscribers_for_hour(6)) == {"111", "222"}


def test_get_subscribers_for_hour_no_match():
    from db import get_subscribers_for_hour
    assert get_subscribers_for_hour(14) == []


def test_set_delivery_hour_updates_value():
    from db import add_subscriber, set_delivery_hour, get_subscriber
    add_subscriber("111", hour_eat=6)
    assert set_delivery_hour("111", 9) is True
    assert get_subscriber("111")["hour_eat"] == 9


def test_set_delivery_hour_not_found():
    from db import set_delivery_hour
    assert set_delivery_hour("999", 9) is False


def test_get_subscriber_returns_all_fields():
    from db import add_subscriber, get_subscriber
    add_subscriber("111", hour_eat=7)
    sub = get_subscriber("111")
    assert sub["chat_id"] == "111"
    assert sub["hour_eat"] == 7
    assert sub["source"] == "command"
    assert "joined_at" in sub


def test_get_subscriber_not_found():
    from db import get_subscriber
    assert get_subscriber("999") is None


def test_seed_from_env_populates_empty_db():
    from db import seed_from_env, get_subscribers_for_hour
    count = seed_from_env(["111", "222"], default_hour=5)
    assert count == 2
    assert set(get_subscribers_for_hour(5)) == {"111", "222"}


def test_seed_from_env_sets_source_env_seed():
    from db import seed_from_env, get_subscriber
    seed_from_env(["111"])
    assert get_subscriber("111")["source"] == "env_seed"


def test_seed_from_env_skips_when_db_not_empty():
    from db import add_subscriber, seed_from_env, get_subscriber
    add_subscriber("existing")
    count = seed_from_env(["111", "222"])
    assert count == 0
    assert get_subscriber("111") is None


def test_seed_from_env_empty_list():
    from db import seed_from_env
    assert seed_from_env([]) == 0


def test_seed_from_env_skips_blank_strings():
    from db import seed_from_env, get_subscribers_for_hour
    count = seed_from_env(["111", "  ", "222"])
    assert count == 2
```

- [ ] **Step 5: Run tests — confirm they all fail**

```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'` (db.py doesn't exist yet).

- [ ] **Step 6: Create `db.py`**

```python
"""SQLite subscriber store. One table, stdlib sqlite3 only."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from config import get_db_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create schema if not exists. Safe to call on every startup."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id    TEXT    PRIMARY KEY,
                hour_eat   INTEGER NOT NULL DEFAULT 6,
                joined_at  TEXT    NOT NULL,
                source     TEXT    NOT NULL DEFAULT 'command'
            )
        """)
        conn.commit()
    finally:
        conn.close()


def seed_from_env(chat_ids: list[str], *, default_hour: int = 6) -> int:
    """Insert chat_ids into an empty table (source='env_seed'). No-ops if table has rows."""
    if not chat_ids:
        return 0
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
        if count > 0:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        for chat_id in [c.strip() for c in chat_ids if c.strip()]:
            cur = conn.execute(
                "INSERT OR IGNORE INTO subscribers (chat_id, hour_eat, joined_at, source)"
                " VALUES (?, ?, ?, ?)",
                (chat_id, default_hour, now, "env_seed"),
            )
            inserted += cur.rowcount
        conn.commit()
        return inserted
    finally:
        conn.close()


def add_subscriber(chat_id: str, *, hour_eat: int = 6) -> bool:
    """Insert subscriber. Returns True if newly inserted, False if already existed."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, hour_eat, joined_at, source)"
            " VALUES (?, ?, ?, ?)",
            (chat_id, hour_eat, now, "command"),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def remove_subscriber(chat_id: str) -> bool:
    """Delete subscriber. Returns True if a row was deleted."""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_delivery_hour(chat_id: str, hour_eat: int) -> bool:
    """Update delivery hour for an existing subscriber. Returns True if found and updated."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE subscribers SET hour_eat = ? WHERE chat_id = ?",
            (hour_eat, chat_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_subscribers_for_hour(hour_eat: int) -> list[str]:
    """Return chat_ids whose stored delivery hour matches hour_eat."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT chat_id FROM subscribers WHERE hour_eat = ?", (hour_eat,)
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_subscriber(chat_id: str) -> dict[str, Any] | None:
    """Return subscriber row as dict, or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT chat_id, hour_eat, joined_at, source FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
```

- [ ] **Step 7: Run tests — confirm they all pass**

```bash
./venv/bin/pytest tests/test_db.py -v
```

Expected: all 19 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add requirements-dev.txt tests/__init__.py tests/test_db.py config.py db.py
git commit -m "feat: add SQLite subscriber store and DB_PATH config"
```

---

## Task 2: Bot commands — `/subscribe`, `/unsubscribe`, `/settime`

**Files:**
- Modify: `commands.py`
- Create: `tests/test_commands.py`

**Interfaces:**
- Consumes:
  - `add_subscriber(chat_id: str, *, hour_eat: int = 6) -> bool` from `db.py`
  - `remove_subscriber(chat_id: str) -> bool` from `db.py`
  - `set_delivery_hour(chat_id: str, hour_eat: int) -> bool` from `db.py`
  - `get_subscriber(chat_id: str) -> dict | None` from `db.py`
- Produces:
  - All existing handler signatures updated: `handler(args: str, chat_id: str = "") -> list[str]`
  - `handle_message_text(text: str, chat_id: str = "") -> list[str] | None`
  - `handle_subscribe(args: str, chat_id: str = "") -> list[str]`
  - `handle_unsubscribe(args: str, chat_id: str = "") -> list[str]`
  - `handle_settime(args: str, chat_id: str = "") -> list[str]`

- [ ] **Step 1: Write failing tests**

Create `tests/test_commands.py`:

```python
"""Tests for subscribe/unsubscribe/settime command handlers."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


# --- /subscribe ---

def test_subscribe_new_default_hour():
    from commands import handle_subscribe
    msgs = handle_subscribe("", chat_id="42")
    assert len(msgs) == 1
    assert "6:00 EAT" in msgs[0]
    assert "✅" in msgs[0]


def test_subscribe_custom_hour():
    from commands import handle_subscribe
    msgs = handle_subscribe("9", chat_id="42")
    assert "9:00 EAT" in msgs[0]
    assert "✅" in msgs[0]


def test_subscribe_hour_zero():
    from commands import handle_subscribe
    msgs = handle_subscribe("0", chat_id="42")
    assert "0:00 EAT" in msgs[0]


def test_subscribe_hour_23():
    from commands import handle_subscribe
    msgs = handle_subscribe("23", chat_id="42")
    assert "23:00 EAT" in msgs[0]


def test_subscribe_already_subscribed():
    from commands import handle_subscribe
    handle_subscribe("", chat_id="42")
    msgs = handle_subscribe("", chat_id="42")
    assert "already subscribed" in msgs[0].lower()
    assert "6:00 EAT" in msgs[0]


def test_subscribe_invalid_hour_too_high():
    from commands import handle_subscribe
    msgs = handle_subscribe("25", chat_id="42")
    assert "0" in msgs[0] and "23" in msgs[0]


def test_subscribe_invalid_hour_negative():
    from commands import handle_subscribe
    msgs = handle_subscribe("-1", chat_id="42")
    assert "0" in msgs[0] and "23" in msgs[0]


def test_subscribe_non_numeric_hour():
    from commands import handle_subscribe
    msgs = handle_subscribe("morning", chat_id="42")
    assert len(msgs) == 1
    assert "number" in msgs[0].lower() or "morning" in msgs[0].lower()


# --- /unsubscribe ---

def test_unsubscribe_existing():
    from commands import handle_subscribe, handle_unsubscribe
    handle_subscribe("", chat_id="42")
    msgs = handle_unsubscribe("", chat_id="42")
    assert "unsubscribed" in msgs[0].lower()


def test_unsubscribe_not_subscribed():
    from commands import handle_unsubscribe
    msgs = handle_unsubscribe("", chat_id="42")
    assert "not subscribed" in msgs[0].lower() or "weren't subscribed" in msgs[0].lower()


def test_unsubscribe_removes_from_db():
    from commands import handle_subscribe, handle_unsubscribe
    from db import get_subscriber
    handle_subscribe("", chat_id="42")
    handle_unsubscribe("", chat_id="42")
    assert get_subscriber("42") is None


# --- /settime ---

def test_settime_updates_hour():
    from commands import handle_subscribe, handle_settime
    from db import get_subscriber
    handle_subscribe("", chat_id="42")
    handle_settime("9", chat_id="42")
    assert get_subscriber("42")["hour_eat"] == 9


def test_settime_reply_confirms_new_hour():
    from commands import handle_subscribe, handle_settime
    handle_subscribe("", chat_id="42")
    msgs = handle_settime("9", chat_id="42")
    assert "9:00 EAT" in msgs[0]
    assert "✅" in msgs[0]


def test_settime_not_subscribed():
    from commands import handle_settime
    msgs = handle_settime("9", chat_id="42")
    assert "not subscribed" in msgs[0].lower()


def test_settime_missing_hour():
    from commands import handle_subscribe, handle_settime
    handle_subscribe("", chat_id="42")
    msgs = handle_settime("", chat_id="42")
    assert "hour" in msgs[0].lower() or "provide" in msgs[0].lower()


def test_settime_invalid_hour():
    from commands import handle_subscribe, handle_settime
    handle_subscribe("", chat_id="42")
    msgs = handle_settime("99", chat_id="42")
    assert "0" in msgs[0] and "23" in msgs[0]


# --- signature compatibility (existing handlers must accept chat_id) ---

def test_handle_help_accepts_chat_id():
    from commands import handle_help
    result = handle_help("", chat_id="99")
    assert isinstance(result, list)
    assert len(result) > 0


def test_handle_start_accepts_chat_id():
    from commands import handle_start
    result = handle_start("", chat_id="99")
    assert isinstance(result, list)


def test_handle_message_text_routes_subscribe():
    from commands import handle_message_text
    msgs = handle_message_text("/subscribe", chat_id="42")
    assert msgs is not None
    assert "✅" in msgs[0] or "subscribed" in msgs[0].lower()


def test_handle_message_text_routes_unsubscribe():
    from commands import handle_message_text
    handle_message_text("/subscribe", chat_id="42")
    msgs = handle_message_text("/unsubscribe", chat_id="42")
    assert msgs is not None
    assert "unsubscribed" in msgs[0].lower()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
./venv/bin/pytest tests/test_commands.py -v
```

Expected: most tests fail with `TypeError` (missing `chat_id`) or `ImportError` (new handlers not defined yet).

- [ ] **Step 3: Update `commands.py`**

**3a — Add imports at top of file** (after existing imports):

```python
from db import add_subscriber, get_subscriber, remove_subscriber, set_delivery_hour
```

**3b — Add `_parse_hour` helper** (before the handler functions):

```python
def _parse_hour(args: str) -> int | str:
    """Return int 0–23 on success, or an HTML error string."""
    args = args.strip()
    if not args:
        return "Please provide an hour, e.g. <code>/settime 9</code>."
    try:
        hour = int(args)
    except ValueError:
        return (
            f""{args}" isn't a number. "
            "Please give an hour 0–23, e.g. <code>/settime 9</code>."
        )
    if not 0 <= hour <= 23:
        return "Please give an hour between 0 and 23, e.g. <code>/settime 9</code>."
    return hour
```

**3c — Add new handlers** (after `handle_chapter`):

```python
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
```

**3d — Update `BOT_COMMANDS`** (add three entries):

```python
BOT_COMMANDS = [
    {"command": "start",       "description": "Welcome and command list"},
    {"command": "help",        "description": "Full help and examples"},
    {"command": "today",       "description": "Today's plan reading"},
    {"command": "day",         "description": "Reading for a date, e.g. 17 may"},
    {"command": "verse",       "description": "Look up a verse, e.g. John 3:16"},
    {"command": "chapter",     "description": "Look up a chapter, e.g. John 3"},
    {"command": "subscribe",   "description": "Get daily readings (e.g. /subscribe 8 for 8am)"},
    {"command": "unsubscribe", "description": "Stop daily readings"},
    {"command": "settime",     "description": "Change delivery hour, e.g. /settime 9"},
]
```

**3e — Add `chat_id` param to all existing handlers** (default `""` keeps call sites that omit it working):

```python
def handle_start(_args: str, chat_id: str = "") -> list[str]:
def handle_help(_args: str, chat_id: str = "") -> list[str]:
def handle_today(_args: str, chat_id: str = "") -> list[str]:
def handle_day(args: str, chat_id: str = "") -> list[str]:
def handle_verse(args: str, chat_id: str = "") -> list[str]:
def handle_chapter(args: str, chat_id: str = "") -> list[str]:
```

**3f — Update `HANDLERS` dict** (add new entries):

```python
HANDLERS: dict[str, Callable[[str, str], list[str]]] = {
    "start":       handle_start,
    "help":        handle_help,
    "today":       handle_today,
    "day":         handle_day,
    "verse":       handle_verse,
    "chapter":     handle_chapter,
    "subscribe":   handle_subscribe,
    "unsubscribe": handle_unsubscribe,
    "settime":     handle_settime,
}
```

**3g — Update `handle_message_text` signature**:

```python
def handle_message_text(text: str, chat_id: str = "") -> list[str] | None:
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
```

**3h — Update `HELP_TEXT`** to mention the new commands (replace the `<b>Commands</b>` block):

```python
HELP_TEXT = """📖 <b>Daily Bread Bot</b>

<b>Reading commands</b>
/today — today's reading (52-week plan)
/day 17 may — reading for a date (current year)
/verse John 3:16 — a verse or range
/chapter John 3 — a full chapter (or Rom 1-2)

<b>Daily delivery</b>
/subscribe — get the daily reading (default 6am EAT)
/subscribe 8 — subscribe with 8am delivery
/settime 9 — change your delivery hour
/unsubscribe — stop daily readings

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
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_commands.py -v
```

Expected: all 22 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add commands.py tests/test_commands.py
git commit -m "feat: add /subscribe, /unsubscribe, /settime commands"
```

---

## Task 3: Daily dispatch — query DB instead of env

**Files:**
- Modify: `daily_bread.py`
- Modify: `telegram_client.py`
- Create: `tests/test_daily_bread.py`

**Interfaces:**
- Consumes:
  - `get_subscribers_for_hour(hour_eat: int) -> list[str]` from `db.py`
  - `send_messages(chat_id: str | int, messages: str | list[str]) -> bool` from `telegram_client.py`
- Produces:
  - `_get_current_hour_eat() -> int` in `daily_bread.py` (testable seam)
  - `_get_recipients() -> list[str]` in `daily_bread.py` (testable seam)

- [ ] **Step 1: Write failing tests**

Create `tests/test_daily_bread.py`:

```python
"""Tests for daily_bread.py dispatch logic."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    from db import init_db
    init_db()


def test_get_recipients_returns_matching_hour(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=9)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    from daily_bread import _get_recipients
    assert _get_recipients() == ["111"]


def test_get_recipients_empty_when_no_match(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 14)

    from daily_bread import _get_recipients
    assert _get_recipients() == []


def test_get_recipients_multiple_at_same_hour(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=8)
    add_subscriber("222", hour_eat=8)
    add_subscriber("333", hour_eat=9)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 8)

    from daily_bread import _get_recipients
    assert set(_get_recipients()) == {"111", "222"}


def test_main_exits_early_when_no_subscribers(monkeypatch, capsys):
    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 3)

    import daily_bread
    daily_bread.main()

    captured = capsys.readouterr()
    assert "nothing to send" in captured.out.lower() or "no subscribers" in captured.out.lower()


def test_main_sends_to_matching_subscribers(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    sent_to = []

    def mock_send(chat_id, messages, **kwargs):
        sent_to.append(str(chat_id))
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
        lambda *a, **kw: ["reading message"],
    )

    import daily_bread
    daily_bread.main()

    assert "111" in sent_to


def test_main_does_not_send_to_non_matching_hour(monkeypatch):
    from db import add_subscriber
    add_subscriber("111", hour_eat=6)
    add_subscriber("222", hour_eat=9)

    monkeypatch.setattr("daily_bread._get_current_hour_eat", lambda: 6)

    sent_to = []

    def mock_send(chat_id, messages, **kwargs):
        sent_to.append(str(chat_id))
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
        lambda *a, **kw: ["reading message"],
    )

    import daily_bread
    daily_bread.main()

    assert "111" in sent_to
    assert "222" not in sent_to
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
./venv/bin/pytest tests/test_daily_bread.py -v
```

Expected: `ImportError` — `_get_current_hour_eat` and `_get_recipients` don't exist yet.

- [ ] **Step 3: Rewrite `daily_bread.py`**

Replace the entire file:

```python
#!/usr/bin/env python3
"""Daily cron entrypoint: push today's plan reading to subscribed chats.

Cron fires every hour (top of hour). This script queries the subscriber DB
for chat_ids whose delivery hour matches the current EAT hour, then sends.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bible_client import fetch_bible_text
from config import TIMEZONE
from db import get_subscribers_for_hour
from formatting import build_reading_messages
from plan_reader import get_eat_today, get_reference_for_today
from telegram_client import send_messages


def _get_current_hour_eat() -> int:
    return datetime.now(ZoneInfo(TIMEZONE)).hour


def _get_recipients() -> list[str]:
    return get_subscribers_for_hour(_get_current_hour_eat())


def main() -> None:
    chat_ids = _get_recipients()

    if not chat_ids:
        hour = _get_current_hour_eat()
        print(f"No subscribers for {hour}:00 EAT — nothing to send.")
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

    label = f"Week {plan_week} • {day_name}: {ref}"
    if sent:
        print(f"✅ Sent to {sent}/{len(chat_ids)} subscribers → {label}")
    else:
        print(f"❌ Failed to send to all {len(chat_ids)} subscribers → {label}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Remove `send_to_configured_chats` from `telegram_client.py`**

Delete the entire `send_to_configured_chats` function (lines 80–95 in the current file) and remove the `get_chat_ids` import at the top.

The `get_chat_ids` import line to remove:
```python
    get_chat_ids,
```

The function block to remove:
```python
def send_to_configured_chats(messages: str | list[str]) -> bool:
    """Daily push: send to all TELEGRAM_CHAT_IDS."""
    token = get_bot_token()
    chat_ids = get_chat_ids()
    if is_placeholder_token(token):
        log_event("send_failed", reason="missing_or_placeholder_token")
        return False
    if not chat_ids:
        log_event("send_failed", reason="no_chat_ids")
        return False

    sent_any = False
    for chat_id in chat_ids:
        if send_messages(chat_id, messages, token=token):
            sent_any = True
    return sent_any
```

- [ ] **Step 5: Run tests — confirm they pass**

```bash
./venv/bin/pytest tests/test_daily_bread.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Run full test suite — confirm nothing regressed**

```bash
./venv/bin/pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add daily_bread.py telegram_client.py tests/test_daily_bread.py
git commit -m "feat: dispatch daily readings from subscriber DB by EAT hour"
```

---

## Task 4: Bot startup wiring + infrastructure

**Files:**
- Modify: `bot_app.py`
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Modify: `.gitignore`
- Modify: `.env.example`

**Interfaces:**
- Consumes:
  - `init_db() -> None` from `db.py`
  - `seed_from_env(chat_ids: list[str], *, default_hour: int = 6) -> int` from `db.py`
  - `get_chat_ids() -> list[str]` from `config.py`
  - `handle_message_text(text: str, chat_id: str = "") -> list[str] | None` from `commands.py`

- [ ] **Step 1: Update `bot_app.py` lifespan**

In the `lifespan` function, add after the webhook registration block and before `log_event("startup_ready", ...)`:

```python
    from db import init_db, seed_from_env
    from config import get_chat_ids

    init_db()
    seeded = seed_from_env(get_chat_ids())
    if seeded:
        log_event("subscribers_seeded_from_env", count=seeded)
```

- [ ] **Step 2: Update the `handle_message_text` call in `bot_app.py`**

Find this line (inside the `webhook` route handler):

```python
        replies = handle_message_text(text)
```

Replace with:

```python
        replies = handle_message_text(text, chat_id=str(chat_id))
```

Also find the fallback call two lines below it:

```python
                replies = handle_message_text("/help") or [
```

This fallback doesn't need `chat_id` (it's just `/help`), leave it as-is.

- [ ] **Step 3: Update `docker-compose.yml` — add named volume**

Add a `volumes` key under the `bot` service and declare the named volume at the bottom:

```yaml
services:
  bot:
    # ... existing config ...
    volumes:
      - bible-data:/data

volumes:
  bible-data:
```

- [ ] **Step 4: Update `Dockerfile` — copy `db.py` and create `/data`**

In the `COPY` line, add `db.py`:

```dockerfile
COPY config.py bible_client.py plan_reader.py formatting.py \
     telegram_client.py commands.py bot_app.py daily_bread.py \
     discover_chats.py debug_webhook.py logutil.py db.py plan.json ./
```

Add a `RUN` to create and own `/data` before the `useradd` step (or after, with the right chown). Insert after the `useradd` line:

```dockerfile
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
```

(This replaces the existing `&& chown -R appuser:appuser /app` line.)

- [ ] **Step 5: Update `.gitignore`**

Add `data/` on its own line (the DB file must not be committed):

```
data/
```

- [ ] **Step 6: Update `.env.example`**

Replace the `TELEGRAM_CHAT_IDS` block and add `DB_PATH` note:

```bash
# Used ONLY to seed the subscriber database on first startup (when the table is empty).
# After the first deploy, these chat IDs will be in the DB — you can remove this line.
# Format: comma-separated Telegram chat IDs.
TELEGRAM_CHAT_IDS=123456789,987654321

# Optional: override the DB file path inside the container (default: /data/bible.db).
# Only set this if you know what you're doing — the Docker volume handles persistence.
# DB_PATH=/data/bible.db
```

- [ ] **Step 7: Commit**

```bash
git add bot_app.py docker-compose.yml Dockerfile .gitignore .env.example
git commit -m "feat: wire DB init and subscriber seeding into bot startup"
```

---

## Task 5: VPS deployment and migration

This task has no code changes. It is a step-by-step checklist for deploying to the VPS and verifying the migration.

**Run all steps on the VPS as the `deploy` user.**

- [ ] **Step 1: Pull and rebuild**

```bash
cd ~/opt/bible
git pull
docker compose build --no-cache
docker compose up -d
```

- [ ] **Step 2: Verify the container is healthy**

```bash
docker ps | grep bible-bot
# Should show: Up X seconds (healthy)
```

- [ ] **Step 3: Verify DB was created and seeded**

```bash
docker compose exec -T bot python -c "import sqlite3,os; rows=sqlite3.connect(os.getenv('DB_PATH','/data/bible.db')).execute('SELECT * FROM subscribers').fetchall(); print(rows)"
```

Expected: one row per chat ID from `TELEGRAM_CHAT_IDS` in `.env`, with `hour_eat=6` and `source=env_seed`.

If the table is empty, check startup logs:

```bash
docker logs bible-bot --tail 50 | grep -E "seed|subscriber|error"
```

- [ ] **Step 4: Test `/subscribe` and `/unsubscribe` live**

Open Telegram, send `/subscribe 7` to the bot. Expected reply: `✅ You're subscribed! You'll get your daily reading at 7:00 EAT.`

Send `/unsubscribe`. Expected reply: `You've been unsubscribed.`

Send `/subscribe` (no hour). Expected reply: confirms 6:00 EAT default.

Verify in DB:

```bash
docker compose exec -T bot python -c "import sqlite3,os; rows=sqlite3.connect(os.getenv('DB_PATH','/data/bible.db')).execute('SELECT chat_id,hour_eat,source FROM subscribers').fetchall(); print(rows)"
```

- [ ] **Step 5: Test dry-run dispatch manually**

Pick a subscriber's `chat_id` and hour. Temporarily set one subscriber's hour to the current EAT hour (or just run the script and check output):

```bash
docker compose exec -T bot python daily_bread.py
```

Expected output: `✅ Sent to 1/N subscribers → Week X • DayName: Ref` (or "No subscribers" if no match for current hour).

- [ ] **Step 6: Update cron entry**

```bash
crontab -e
```

Replace:

```
30 4 * * * ~/opt/bible/run_daily_docker.sh
```

With:

```
0 * * * * ~/opt/bible/run_daily_docker.sh >> ~/opt/bible/daily_bread.log 2>&1
```

Verify the new crontab:

```bash
crontab -l | grep bible
```

- [ ] **Step 7: Remove `TELEGRAM_CHAT_IDS` from `.env`**

Once the DB is confirmed seeded, remove the line from `.env` on the VPS (the env var is no longer read during dispatch):

```bash
nano ~/opt/bible/.env
# Delete the TELEGRAM_CHAT_IDS= line
```

Restart to confirm startup still works without it:

```bash
docker compose restart bot
docker logs bible-bot --tail 20
```

Expected: no error about missing chat IDs — startup log should show `subscribers_seeded_from_env` with `count: 0` (table not empty, so seeding skipped).

---

## Self-Review Checklist

- [x] **Spec coverage:** All spec sections mapped — `db.py` (Task 1), command handlers (Task 2), daily dispatch (Task 3), lifespan wiring + Docker (Task 4), VPS migration (Task 5)
- [x] **Placeholder scan:** No TBD, no "add appropriate validation", all test assertions are concrete
- [x] **Type consistency:** `chat_id` is `str` throughout (stored as TEXT, passed as `str`). `hour_eat` is `int` throughout. `get_subscriber` returns `dict | None` — matches usage in Task 2 handlers. `_get_current_hour_eat() -> int` defined in Task 3, used in Task 3 test monkeypatching. `send_messages` signature unchanged from `telegram_client.py`.
- [x] **Named volume:** `bible-data` named consistently in `docker-compose.yml` description and Dockerfile task
- [x] **`seed_from_env` called correctly:** `seed_from_env(get_chat_ids())` in `bot_app.py` Task 4 Step 1 matches signature `seed_from_env(chat_ids: list[str], *, default_hour: int = 6) -> int` defined in Task 1
