#!/usr/bin/env python3
"""Diagnose Telegram webhook + local app secret alignment.

Run on the VPS (same env as the bot):

  docker compose exec bot python debug_webhook.py

Or on a machine with the same .env:

  python debug_webhook.py
"""

from __future__ import annotations

import json
import sys

import requests

from config import (
    get_bot_token,
    get_webhook_secret,
    get_webhook_url,
    is_placeholder_token,
)
from telegram_client import get_webhook_info, register_bot_webhook


def main() -> int:
    token = get_bot_token()
    url = get_webhook_url()
    secret = get_webhook_secret()

    print("=== config (no secrets printed) ===")
    print(f"  token_set:           {bool(token) and not is_placeholder_token(token)}")
    print(f"  WEBHOOK_URL:         {url or '(empty)'}")
    print(f"  WEBHOOK_SECRET set:  {bool(secret)} (len={len(secret)})")
    print()

    if is_placeholder_token(token):
        print("ERROR: TELEGRAM_BOT_TOKEN missing or placeholder.")
        return 1

    print("=== getWebhookInfo (before) ===")
    try:
        before = get_webhook_info(token=token)
        print(json.dumps(before.get("result") or before, indent=2))
    except Exception as e:
        print(f"ERROR getWebhookInfo: {e}")
        return 1
    print()

    if not url:
        print("ERROR: WEBHOOK_URL is empty. Set e.g.")
        print("  WEBHOOK_URL=https://bible.samtama.lol/webhook")
        return 1

    print("=== register_bot_webhook (setWebhook + info) ===")
    result = register_bot_webhook(
        url, secret_token=secret or None, token=token
    )
    print("setWebhook:", json.dumps(result.get("set"), indent=2))
    info = (result.get("info") or {}).get("result") or {}
    print("getWebhookInfo:", json.dumps(info, indent=2))
    print()

    public = url
    print(f"=== probe POST {public} ===")
    payload = {
        "update_id": 900001,
        "message": {
            "message_id": 1,
            "from": {"id": 1, "is_bot": False, "first_name": "Debug"},
            "chat": {"id": 1, "type": "private"},
            "date": 1,
            "text": "/help",
        },
    }

    status_with: int | None = None
    status_without: int | None = None

    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
        try:
            r = requests.post(public, json=payload, headers=headers, timeout=45)
            status_with = r.status_code
            print(f"  with secret header:  HTTP {r.status_code}  {r.text[:200]}")
        except Exception as e:
            print(f"  with secret header:  ERROR {e}")
    else:
        print("  with secret header:  (skipped — WEBHOOK_SECRET empty in this env)")

    try:
        r2 = requests.post(
            public,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=45,
        )
        status_without = r2.status_code
        print(f"  without secret:      HTTP {r2.status_code}  {r2.text[:200]}")
    except Exception as e:
        print(f"  without secret:      ERROR {e}")

    print()
    if secret:
        print("Expected: with secret → 200; without secret → 403")
    else:
        print("Expected: without secret → 200 (open webhook in this env)")

    if status_without == 403 and (status_with is None or status_with == 403):
        print()
        print("!!! SECRET MISMATCH / APP REQUIRES SECRET !!!")
        print("The running app returned 403 Invalid secret token.")
        print("That means the container's WEBHOOK_SECRET does not match what you")
        print("used for this probe (or setWebhook was registered with a different secret).")
        print()
        print("Fix on the VPS (uses the container's real .env):")
        print("  docker compose exec bot python debug_webhook.py")
        print("  docker compose restart bot")
        print("  docker logs bible-bot --tail 50")
        print()
        print("Confirm logs include webhook_register_result ok=true and webhook_info url=...")

    registered_url = info.get("url") or ""
    if registered_url and registered_url.rstrip("/") != url.rstrip("/"):
        print()
        print(f"WARNING: registered URL {registered_url!r} != WEBHOOK_URL {url!r}")

    print()
    print("If getWebhookInfo.url is correct and probe with secret is 200,")
    print("message the bot /help and check: docker logs bible-bot -f")
    print("Look for: webhook_update, send_ok (or send_failed / webhook_secret_rejected)")
    return 0 if (result.get("set") or {}).get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
