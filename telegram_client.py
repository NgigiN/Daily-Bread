"""Thin Telegram Bot API helpers."""

from __future__ import annotations

import time
from typing import Any

import requests

from config import (
    SEND_DELAY_SEC,
    TELEGRAM_API,
    get_bot_token,
    is_placeholder_token,
)
from formatting import split_message
from logutil import log_event

ALLOWED_WEBHOOK_UPDATES = ["message", "edited_message"]


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
        log_event("send_failed", reason="missing_or_placeholder_token", chat_id=chat_id)
        return False

    if isinstance(messages, str):
        messages = [messages]

    endpoint = _url(token, "sendMessage")
    chunks_sent = 0
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
                body = r.json() if r.content else {}
                if r.status_code >= 400 or not body.get("ok"):
                    log_event(
                        "send_failed",
                        chat_id=chat_id,
                        http_status=r.status_code,
                        telegram=body,
                    )
                    return False
                chunks_sent += 1
                time.sleep(SEND_DELAY_SEC)
        log_event(
            "send_ok",
            chat_id=chat_id,
            messages=len(messages),
            chunks=chunks_sent,
        )
        return True
    except Exception as e:
        log_event("send_failed", chat_id=chat_id, error=str(e))
        return False



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
    try:
        body = r.json()
    except Exception:
        r.raise_for_status()
        return {"ok": False, "description": r.text}
    if r.status_code >= 400:
        return {
            "ok": False,
            "description": body.get("description") or r.text,
            "error_code": body.get("error_code"),
            "http_status": r.status_code,
        }
    return body


def set_my_commands(
    commands: list[dict[str, str]], *, token: str | None = None
) -> dict[str, Any]:
    return telegram_api(
        "setMyCommands", token=token, json_body={"commands": commands}
    )


def set_webhook(
    url: str,
    *,
    secret_token: str | None = None,
    token: str | None = None,
    drop_pending_updates: bool = True,
) -> dict[str, Any]:
    """
    Register HTTPS webhook with Telegram.

    secret_token must match WEBHOOK_SECRET in the app. Telegram will send it as
    X-Telegram-Bot-Api-Secret-Token on every update POST. Users never see it.
    """
    payload: dict[str, Any] = {
        "url": url,
        "allowed_updates": ALLOWED_WEBHOOK_UPDATES,
        "drop_pending_updates": drop_pending_updates,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    return telegram_api("setWebhook", token=token, json_body=payload)


def get_webhook_info(*, token: str | None = None) -> dict[str, Any]:
    token = token if token is not None else get_bot_token()
    r = requests.get(_url(token, "getWebhookInfo"), timeout=30)
    r.raise_for_status()
    return r.json()


def delete_webhook(
    *, drop_pending_updates: bool = False, token: str | None = None
) -> dict[str, Any]:
    return telegram_api(
        "deleteWebhook",
        token=token,
        json_body={"drop_pending_updates": drop_pending_updates},
    )


def register_bot_webhook(
    webhook_url: str,
    *,
    secret_token: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """
    setWebhook + getWebhookInfo with structured logs.
    Returns {"set": setWebhook body, "info": getWebhookInfo result}.
    """
    secret_on = bool(secret_token)
    log_event(
        "webhook_register_start",
        url=webhook_url,
        secret_configured=secret_on,
    )
    set_body = set_webhook(
        webhook_url, secret_token=secret_token or None, token=token
    )
    log_event(
        "webhook_register_result",
        ok=bool(set_body.get("ok")),
        description=set_body.get("description"),
        error_code=set_body.get("error_code"),
        url=webhook_url,
        secret_configured=secret_on,
    )

    info_body: dict[str, Any] = {}
    try:
        info_body = get_webhook_info(token=token)
        result = info_body.get("result") or {}
        log_event(
            "webhook_info",
            ok=bool(info_body.get("ok")),
            url=result.get("url"),
            pending_update_count=result.get("pending_update_count"),
            last_error_date=result.get("last_error_date"),
            last_error_message=result.get("last_error_message"),
            ip_address=result.get("ip_address"),
            max_connections=result.get("max_connections"),
            allowed_updates=result.get("allowed_updates"),
        )
    except Exception as e:
        log_event("webhook_info_failed", error=str(e))

    return {"set": set_body, "info": info_body}
