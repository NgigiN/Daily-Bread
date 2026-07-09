"""Thin Telegram Bot API helpers."""

from __future__ import annotations

import time
from typing import Any

import requests

from config import (
    SEND_DELAY_SEC,
    TELEGRAM_API,
    get_bot_token,
    get_chat_ids,
    is_placeholder_token,
)
from formatting import split_message


def _url(token: str, method: str) -> str:
    return TELEGRAM_API.format(token=token, method=method)


def send_messages(
    chat_id: str | int,
    messages: str | list[str],
    *,
    token: str | None = None,
) -> bool:
    """Send one or more HTML messages to a single chat."""
    token = token if token is not None else get_bot_token()
    if is_placeholder_token(token):
        print("❌ Set TELEGRAM_BOT_TOKEN in .env")
        return False

    if isinstance(messages, str):
        messages = [messages]

    endpoint = _url(token, "sendMessage")
    try:
        for message in messages:
            for chunk in split_message(message):
                r = requests.post(
                    endpoint,
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
                    return False
                time.sleep(SEND_DELAY_SEC)
        return True
    except Exception as e:
        print(f"❌ Telegram send error for {chat_id}: {e}")
        return False


def send_to_configured_chats(messages: str | list[str]) -> bool:
    """Daily push: send to all TELEGRAM_CHAT_IDS."""
    token = get_bot_token()
    chat_ids = get_chat_ids()
    if is_placeholder_token(token):
        print("❌ Set TELEGRAM_BOT_TOKEN in .env")
        return False
    if not chat_ids:
        print("❌ Set TELEGRAM_CHAT_IDS in .env (run discover_chats.py)")
        return False

    sent_any = False
    for chat_id in chat_ids:
        if send_messages(chat_id, messages, token=token):
            sent_any = True
    return sent_any


def telegram_api(
    method: str,
    *,
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = token if token is not None else get_bot_token()
    r = requests.post(
        _url(token, method),
        json=json_body,
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def set_my_commands(commands: list[dict[str, str]], *, token: str | None = None) -> bool:
    body = telegram_api("setMyCommands", token=token, json_body={"commands": commands})
    return bool(body.get("ok"))


def set_webhook(
    url: str,
    *,
    secret_token: str | None = None,
    token: str | None = None,
) -> bool:
    payload: dict[str, Any] = {"url": url}
    if secret_token:
        payload["secret_token"] = secret_token
    body = telegram_api("setWebhook", token=token, json_body=payload)
    return bool(body.get("ok"))
