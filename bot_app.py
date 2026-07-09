#!/usr/bin/env python3
"""FastAPI Telegram webhook server for interactive Bible commands."""

from __future__ import annotations

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
from telegram_client import send_messages, set_my_commands, set_webhook


@asynccontextmanager
async def lifespan(_app: FastAPI):
    token = get_bot_token()
    if not is_placeholder_token(token):
        try:
            set_my_commands(BOT_COMMANDS, token=token)
            print("✅ Bot commands registered")
        except Exception as e:
            print(f"⚠️ setMyCommands failed: {e}")

        webhook_url = get_webhook_url()
        if webhook_url:
            try:
                secret = get_webhook_secret() or None
                set_webhook(webhook_url, secret_token=secret, token=token)
                print(f"✅ Webhook set → {webhook_url}")
            except Exception as e:
                print(f"⚠️ setWebhook failed: {e}")
    yield


app = FastAPI(
    title="Daily Bread Bot",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _verify_secret(header_value: str | None) -> None:
    expected = get_webhook_secret()
    if not expected:
        return
    if header_value != expected:
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
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

    message = _extract_message(update)
    if not message:
        return JSONResponse({"ok": True})

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None or not text:
        return JSONResponse({"ok": True})

    replies = handle_message_text(text)
    if replies is None:
        # Plain text that is not a command — point users at help
        if text.startswith("/"):
            replies = handle_message_text("/help") or []
        else:
            replies = [
                "Send a command to get started. Try /help or /today."
            ]

    # Blocking I/O (bible-api + telegram); fine for low traffic
    send_messages(chat_id, replies)
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
