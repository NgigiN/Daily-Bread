"""Shared configuration and constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root (directory containing this file)
ROOT_DIR = Path(__file__).resolve().parent
PLAN_FILE = ROOT_DIR / "plan.json"

BIBLE_API = "https://bible-api.com/"
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

MAX_MESSAGE_LEN = 4096
MAX_CHAPTERS = 150
MAX_CHAPTERS_PER_REQUEST = 6
VERSE_RANGE_END = 200

# bible-api.com: 15 requests / 30 seconds per IP
FETCH_MIN_INTERVAL_SEC = 0.5
RATE_LIMIT_REQUESTS = 14
RATE_LIMIT_WINDOW_SEC = 30.0
MAX_FETCH_RETRIES = 4

SEND_DELAY_SEC = 0.35
CACHE_TTL_SEC = 3600

TIMEZONE = "Africa/Nairobi"


def _strip_env(value: str | None) -> str:
    """Strip whitespace and optional surrounding quotes from env values."""
    if not value:
        return ""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def get_bot_token() -> str:
    return _strip_env(os.getenv("TELEGRAM_BOT_TOKEN"))


def get_chat_ids() -> list[str]:
    raw = _strip_env(os.getenv("TELEGRAM_CHAT_IDS"))
    return [cid.strip() for cid in raw.split(",") if cid.strip()]


def get_webhook_url() -> str:
    return _strip_env(os.getenv("WEBHOOK_URL"))


def get_webhook_secret() -> str:
    return _strip_env(os.getenv("WEBHOOK_SECRET"))


def get_app_host() -> str:
    return os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"


def get_app_port() -> int:
    raw = os.getenv("APP_PORT", "5555").strip() or "5555"
    return int(raw)


def is_placeholder_token(token: str) -> bool:
    return not token or token.startswith("123456789")
