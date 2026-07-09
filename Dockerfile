# syntax=docker/dockerfile:1
# Small production image for the Telegram webhook bot.
# Host publishes only 127.0.0.1:5555 (nginx → container).

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System CA certs only (HTTPS to Telegram + bible-api.com)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer (cached until requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (plan.json required at runtime)
COPY config.py bible_client.py plan_reader.py formatting.py \
     telegram_client.py commands.py bot_app.py daily_bread.py \
     discover_chats.py plan.json ./

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

# Inside the container listen on all interfaces; host bind stays 127.0.0.1
ENV APP_HOST=0.0.0.0 \
    APP_PORT=5555

EXPOSE 5555

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5555/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "bot_app:app", "--host", "0.0.0.0", "--port", "5555"]
