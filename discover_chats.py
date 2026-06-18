#!/usr/bin/env python3
"""List chat IDs from users who have messaged your bot"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token.startswith("123456789"):
        print("Set TELEGRAM_BOT_TOKEN in .env first.")
        sys.exit(1)

    url = TELEGRAM_API.format(token=token, method="getUpdates")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Failed to fetch updates: {e}")
        sys.exit(1)

    if not data.get("ok"):
        print(f"Telegram API error: {data}")
        sys.exit(1)

    seen = {}
    for update in data.get("result", []):
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            continue
        chat = msg["chat"]
        cid = chat["id"]
        if cid in seen:
            continue
        username = chat.get("username") or ""
        name = " ".join(
            filter(None, [chat.get("first_name"), chat.get("last_name")])
        ).strip()
        seen[cid] = (username, name)

    if not seen:
        print("No chats yet. Ask each recipient to:")
        print("  1. Open your bot in Telegram")
        print("  2. Tap Start (or send /start)")
        print("  3. Run this script again")
        sys.exit(0)

    print("Chat IDs for your .env (TELEGRAM_CHAT_IDS=...):")
    print()
    for cid, (username, name) in sorted(seen.items()):
        label = f"@{username}" if username else name or "unknown"
        print(f"  {cid}  ({label})")
    print()
    print("Copy the IDs (comma-separated) into TELEGRAM_CHAT_IDS in .env")


if __name__ == "__main__":
    main()

