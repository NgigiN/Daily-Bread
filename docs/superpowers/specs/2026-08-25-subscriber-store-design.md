# Subscriber Store — Design Spec

**Date:** 2026-08-25  
**Status:** Approved for implementation

---

## Problem

Daily Bible readings are delivered to a hardcoded list of chat IDs in `TELEGRAM_CHAT_IDS` (env var). Adding or removing recipients requires editing `.env` and redeploying. There is no way for users to opt in or out themselves, and no way to choose a personal delivery time.

---

## Goal

Replace the env-var recipient list with a database-backed subscriber store. Users self-manage via bot commands. Each subscriber chooses a delivery hour; the daily script sends to them at that hour only.

---

## Out of Scope

- Per-user timezone support (all times are Africa/Nairobi / EAT, UTC+3)
- Sub-hour granularity (top-of-hour slots only)
- A web admin interface
- Retry-per-subscriber on send failure
- Read receipts or delivery confirmations

---

## Data Model

One SQLite table. No ORM — Python stdlib `sqlite3` only.

```sql
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id    TEXT    PRIMARY KEY,
    hour_eat   INTEGER NOT NULL DEFAULT 6,
    joined_at  TEXT    NOT NULL,
    source     TEXT    NOT NULL DEFAULT 'command'
);
```

| Column | Type | Notes |
|---|---|---|
| `chat_id` | TEXT PK | Telegram chat ID (stored as string; Telegram IDs can exceed int32) |
| `hour_eat` | INTEGER | Delivery hour 0–23 in Africa/Nairobi. Default: 6 (6am EAT) |
| `joined_at` | TEXT | ISO-8601 UTC timestamp of subscription |
| `source` | TEXT | `'command'` for self-subscribed users; `'env_seed'` for migrated chat IDs |

**DB file location:** `/data/bible.db` inside the container, mounted from `./data/` on the host via Docker volume. The `./data/` directory is gitignored.

---

## New File: `db.py`

Single-responsibility module: subscriber persistence only. No Telegram logic, no config knowledge beyond the DB path.

```python
def init_db() -> None
    """Create schema if not exists. Safe to call on every startup."""

def seed_from_env(chat_ids: list[str], *, default_hour: int = 6) -> int:
    """
    Insert chat_ids not already in the DB, sourced as 'env_seed'.
    Only runs when the table is empty (checked before insert).
    Returns count of rows inserted.
    """

def add_subscriber(chat_id: str, *, hour_eat: int = 6) -> bool:
    """
    Insert or ignore (already subscribed).
    Returns True if newly inserted, False if already existed.
    """

def remove_subscriber(chat_id: str) -> bool:
    """
    Delete subscriber. Returns True if a row was deleted, False if not found.
    """

def set_delivery_hour(chat_id: str, hour_eat: int) -> bool:
    """
    Update hour_eat for an existing subscriber.
    Returns True if updated, False if chat_id not found.
    """

def get_subscribers_for_hour(hour_eat: int) -> list[str]:
    """Return list of chat_ids whose hour_eat matches."""

def get_subscriber(chat_id: str) -> dict | None:
    """Return subscriber row dict or None. Used by /settime to check if subscribed."""
```

All functions open and close their own connection. No connection pooling needed at this scale (single-threaded cron caller + async FastAPI writer, never concurrent writers).

---

## Modified Files

### `config.py`

Add one function:

```python
def get_db_path() -> str:
    """Return DB file path. Override via DB_PATH env var; default /data/bible.db."""
    return os.getenv("DB_PATH", "/data/bible.db").strip() or "/data/bible.db"
```

`get_chat_ids()` stays — it is used by `bot_app.py` lifespan for seeding. Remove it only after `TELEGRAM_CHAT_IDS` is cleared from `.env`.

---

### `bot_app.py` — lifespan startup

After the existing webhook registration block, add:

```python
from db import init_db, seed_from_env
from config import get_chat_ids

init_db()
seeded = seed_from_env(get_chat_ids())
if seeded:
    log_event("subscribers_seeded", count=seeded)
```

No other changes to `bot_app.py` beyond updating the `handle_message_text` call site to pass `chat_id`:

```python
replies = handle_message_text(text, chat_id=str(chat_id))
```

---

### `commands.py` — handler signature + new commands

**Signature change (all handlers):**

```python
# Before
def handle_today(_args: str) -> list[str]: ...

# After
def handle_today(_args: str, chat_id: str = "") -> list[str]: ...
```

`chat_id` defaults to `""` so the signature change is backwards-compatible with any direct test calls. Existing handlers ignore it.

`handle_message_text` signature becomes:

```python
def handle_message_text(text: str, chat_id: str = "") -> list[str] | None:
```

**New handlers:**

```python
def handle_subscribe(args: str, chat_id: str = "") -> list[str]:
    """
    /subscribe        → subscribe at default hour 6
    /subscribe 8      → subscribe at 8am EAT
    /subscribe 14     → subscribe at 2pm EAT

    If already subscribed: inform them; suggest /settime to change hour.
    Validates hour is 0–23.
    """

def handle_unsubscribe(_args: str, chat_id: str = "") -> list[str]:
    """
    /unsubscribe → remove from DB.
    If not subscribed: inform them gracefully.
    """

def handle_settime(args: str, chat_id: str = "") -> list[str]:
    """
    /settime 9 → update delivery hour for existing subscriber.
    If not subscribed: prompt them to /subscribe first.
    Validates hour is 0–23.
    """
```

**`BOT_COMMANDS` additions:**

```python
{"command": "subscribe",   "description": "Get daily readings (optional: /subscribe 8 for 8am)"},
{"command": "unsubscribe", "description": "Stop daily readings"},
{"command": "settime",     "description": "Change delivery hour, e.g. /settime 9"},
```

**Hour validation helper (internal):**

```python
def _parse_hour(args: str) -> int | str:
    """
    Parse a string like '8' or '14' into an integer 0–23.
    Returns the int on success, or an error string on failure.
    """
```

**Example reply strings (to be finalised in implementation):**

| Scenario | Reply |
|---|---|
| `/subscribe` (new) | "✅ You're subscribed! You'll get your daily reading at 6am EAT. Change with /settime." |
| `/subscribe 9` (new) | "✅ You're subscribed! You'll get your daily reading at 9am EAT." |
| `/subscribe` (already subscribed) | "You're already subscribed (delivery at Xam EAT). Use /settime to change your hour, or /unsubscribe to stop." |
| `/unsubscribe` (was subscribed) | "You've been unsubscribed. Send /subscribe any time to rejoin." |
| `/unsubscribe` (not subscribed) | "You weren't subscribed. Send /subscribe to sign up." |
| `/settime 9` (subscribed) | "✅ Updated! You'll now get your daily reading at 9am EAT." |
| `/settime 9` (not subscribed) | "You're not subscribed yet. Send /subscribe first." |
| `/settime abc` | "Please give a number 0–23, e.g. /settime 9." |
| `/subscribe 25` | "Please give an hour between 0 and 23, e.g. /subscribe 9." |

---

### `telegram_client.py`

`send_to_configured_chats` gains an explicit `chat_ids` parameter and stops reading from env:

```python
def send_to_all(chat_ids: list[str], messages: str | list[str]) -> bool:
    """Send messages to each chat_id. Returns True if at least one succeeded."""
```

The old `send_to_configured_chats` is removed (only called from `daily_bread.py`, which is rewritten). `get_chat_ids` import in this file is removed.

---

### `daily_bread.py`

Replace env-var dispatch with DB dispatch:

```python
from zoneinfo import ZoneInfo
from datetime import datetime
from db import get_subscribers_for_hour
from telegram_client import send_messages

def main() -> None:
    hour_eat = datetime.now(ZoneInfo("Africa/Nairobi")).hour
    chat_ids = get_subscribers_for_hour(hour_eat)

    if not chat_ids:
        print(f"No subscribers for hour {hour_eat}:00 EAT — nothing to send.")
        return

    today = get_eat_today()
    plan_week, day_name, ref = get_reference_for_today(today)
    # ... (rest of fetch/format logic unchanged) ...

    sent = 0
    for chat_id in chat_ids:
        if send_messages(chat_id, messages):
            sent += 1
    print(f"✅ Sent to {sent}/{len(chat_ids)} subscribers → Week {plan_week} • {day_name}: {ref}")
```

`send_to_configured_chats` is no longer imported here.

---

### `docker-compose.yml`

Add a volume mount under the `bot` service so the DB survives container recreations:

```yaml
services:
  bot:
    volumes:
      - ./data:/data
```

The `./data/` directory is created by Docker on first run. Add `data/` to `.gitignore` (the dir itself; the DB is not committed).

---

### `.env.example`

Update the `TELEGRAM_CHAT_IDS` comment:

```bash
# Used ONLY to seed the subscriber database on first startup (when DB is empty).
# After seeding, this can be removed from .env — the DB is the source of truth.
# Format: comma-separated Telegram chat IDs.
TELEGRAM_CHAT_IDS=123456789,987654321

# Optional: override the DB file path (default: /data/bible.db inside the container)
# DB_PATH=/data/bible.db
```

---

## Cron Entry Change (VPS)

| | Before | After |
|---|---|---|
| Schedule | `30 4 * * *` | `0 * * * *` |
| Meaning | Once daily at 4:30am EAT | Top of every hour |
| Effect | Everyone gets it at 4:30am | Each subscriber gets it at their chosen hour |

No changes to `run_daily_docker.sh` itself — the fix from the earlier session (removing `..` from `cd`) already handles this.

---

## Startup Sequence

1. Container starts → `lifespan()` runs
2. `init_db()` creates schema (no-op if already exists)
3. `seed_from_env(get_chat_ids())` — inserts env chat IDs if table is empty; logs count
4. Webhook and commands registered as before
5. At each top-of-hour: cron fires → `daily_bread.py` queries by current EAT hour → sends to matching subscribers

---

## Migration Path

1. Deploy new code with `./data:/data` volume
2. Container restarts — existing `TELEGRAM_CHAT_IDS` are seeded into DB at hour 6
3. Verify: `docker compose exec -T bot python -c "import sqlite3,os; rows=sqlite3.connect(os.getenv('DB_PATH','/data/bible.db')).execute('SELECT chat_id,hour_eat,source FROM subscribers').fetchall(); print(rows)"`
4. Once confirmed, remove `TELEGRAM_CHAT_IDS` from `.env` and redeploy
5. Update cron entry from `30 4 * * *` to `0 * * * *`

---

## Testing Approach

- `db.py` functions are pure Python / SQLite with no network calls — use an in-memory DB (`:memory:`) in tests
- Command handlers are tested the same way as today (direct function calls), now passing a dummy `chat_id`
- `daily_bread.py` dispatch logic is tested by seeding subscribers with the current EAT hour and asserting sends are triggered
- No mocking of `send_messages` needed for unit tests of command reply strings — those return `list[str]`

---

## Dependencies

No new packages. `sqlite3` and `zoneinfo` are Python stdlib (Python 3.9+). The existing `requirements.txt` is unchanged.

---

## Files Changed Summary

| File | Change type |
|---|---|
| `db.py` | New |
| `config.py` | Add `get_db_path()` |
| `bot_app.py` | Init DB in lifespan; pass `chat_id` to handler |
| `commands.py` | New handlers + signature update |
| `daily_bread.py` | DB-based dispatch |
| `telegram_client.py` | Remove env dependency; add `send_to_all()` |
| `docker-compose.yml` | Add `./data:/data` volume |
| `.env.example` | Update `TELEGRAM_CHAT_IDS` comment; add `DB_PATH` note |
| `.gitignore` | Add `data/` |
