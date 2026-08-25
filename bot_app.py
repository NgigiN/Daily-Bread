#!/usr/bin/env python3
"""FastAPI Telegram webhook server for interactive Bible commands."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    token = get_bot_token()
    if is_placeholder_token(token):
        log_event("startup_warning", reason="TELEGRAM_BOT_TOKEN missing or placeholder")
        yield
        return

    try:
        body = set_my_commands(BOT_COMMANDS, token=token)
        log_event(
            "commands_registered",
            ok=bool(body.get("ok")),
            description=body.get("description"),
        )
    except Exception as e:
        log_event("commands_register_failed", error=str(e))

    webhook_url = get_webhook_url()
    secret = get_webhook_secret()
    if not webhook_url:
        log_event(
            "startup_warning",
            reason="WEBHOOK_URL empty",
        )
    else:
        try:
            register_bot_webhook(
                webhook_url,
                secret_token=secret or None,
                token=token,
            )
        except Exception as e:
            log_event("webhook_register_failed", error=str(e), url=webhook_url)

    from db import init_db, seed_from_env, count_subscribers
    from config import get_chat_ids

    try:
        init_db()
        seeded = seed_from_env(get_chat_ids())
        if seeded:
            log_event("subscribers_seeded_from_env", count=seeded)
        total = count_subscribers()
        log_event("subscriber_count", count=total)
    except Exception as e:
        log_event("db_init_failed", error=str(e))

    log_event(
        "startup_ready",
        webhook_url=webhook_url or None,
        secret_configured=bool(secret),
    )
    yield


app = FastAPI(
    title="Daily Bread Bot",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log_event(
        "request completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=elapsed_ms,
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _verify_secret(header_value: str | None) -> None:
    expected = get_webhook_secret()
    if not expected:
        return
    if header_value != expected:
        log_event(
            "webhook_secret_rejected",
            has_header=bool(header_value),
            header_len=len(header_value) if header_value else 0,
            expected_len=len(expected),
        )
        raise HTTPException(status_code=403, detail="Invalid secret token")


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("edited_message")


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    _verify_secret(x_telegram_bot_api_secret_token)

    try:
        update = await request.json()
    except Exception:
        log_event("webhook_bad_json")
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

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

    log_event(
        "webhook_update",
        update_id=update_id,
        chat_id=chat_id,
        text=text[:200],
    )

    try:
        replies = handle_message_text(text, chat_id=str(chat_id))
        if replies is None:
            if text.startswith("/"):
                replies = handle_message_text("/help") or [
                    "Unknown command. Try /help."
                ]
            else:
                replies = [
                    "Send a command to get started. Try /help or /today."
                ]

        ok = send_messages(chat_id, replies)
        if not ok:
            log_event(
                "webhook_handler_send_failed",
                chat_id=chat_id,
                text=text[:80],
            )
    except Exception as e:
        log_event(
            "webhook_handler_error",
            chat_id=chat_id,
            error=str(e),
            text=text[:80],
        )
        try:
            send_messages(
                chat_id,
                "Sorry, something went wrong handling that command. Try again shortly.",
            )
        except Exception:
            pass

    return JSONResponse({"ok": True})


def main() -> None:
    import uvicorn

    uvicorn.run(
        "bot_app:app",
        host=get_app_host(),
        port=get_app_port(),
        reload=False,
    )


if __name__ == "__main__":
    main()
