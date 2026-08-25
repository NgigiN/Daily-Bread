# Daily Bread

My personal Telegram bot for a 52-week Bible reading plan.

Text via [bible-api.com](https://bible-api.com) (WEB), 

## Architecture

```text
Telegram ──HTTPS──► nginx 
                         │
                         ▼
              127.0.0.1:5555  
                         │
                         ▼
              Docker container bible-bot

Grafana Alloy (VPS) ──► Grafana Cloud Loki
  {job="docker", container="bible-bot"}
```

## Commands

| Command | Example | Purpose |
|---------|---------|---------|
| `/start` | | Welcome |
| `/help` | | Full help |
| `/today` | | Today's plan (EAT) |
| `/day` | `/day 17 may` | Plan for date (current year) |
| `/verse` | `/verse John 3:16` | Verse / range |
| `/chapter` | `/chapter Rom 1-2` | Chapter(s), max 6 |
| `/subscribe` | `/subscribe 8` | Subscribe to daily readings (optional hour) |
| `/unsubscribe` | | Stop daily readings |
| `/settime` | `/settime 9` | Change delivery hour (EAT) |

Interactive use is **open** to anyone who starts the bot.  
`TELEGRAM_CHAT_IDS` seeds the subscriber DB on **first startup only** (when the table is empty).

---

## Local setup (optional, without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   
python bot_app.py     
```

---

## Docker 

### Image goals

- `python:3.12-slim-bookworm`, non-root user
- Small context via `.dockerignore` (no `venv`, `.git`, logs)
- Layer cache: `requirements.txt` installed before app copy
- Healthcheck without extra packages

### Run on the VPS

```bash
cd /path/to/bible          
cp .env.example .env       
docker compose up -d --build

curl http://127.0.0.1:5555/health
docker logs bible-bot --tail 50
```

**Port rule:** compose publishes **`127.0.0.1:5555:5555` only**.  

### Daily push 

```bash
chmod +x deploy/run_daily_docker.sh

# crontab -e
# Runs every hour; each subscriber receives their message at their chosen hour (EAT).
0 * * * *  ~/opt/bible/run_daily_docker.sh >> ~/opt/bible/daily_bread.log 2>&1
```

This runs `docker compose exec -T bot python daily_bread.py` (same image, same `.env`).

---

### One-time VPS prep

1. Clone the repo to `PROJECT_PATH`, install Docker + Compose plugin.
2. Create `.env` there (not in git).
3. Ensure the SSH user can `git fetch`/`pull` (deploy key or HTTPS token) and run `docker` (group membership).
4. Install nginx site + certbot (above).
5. Add cron for daily push.
6. Add GitHub secrets; push to `main`.

---

## Project layout

| Path | Role |
|------|------|
| `bot_app.py` | FastAPI webhook |
| `daily_bread.py` | Daily push entrypoint |
| `commands.py` | Command handlers |
| `bible_client.py` | bible-api.com + rate limit + cache |
| `docker-compose.yml` | `bible-bot` service, loopback publish |
| `Dockerfile` | Slim production image |
| `.github/workflows/deploy.yml` | Deploy on push to main |
| `deploy/nginx/bible.samtama.lol` | nginx site |
| `deploy/run_daily_docker.sh` | Cron helper |
| `debug_webhook.py` | Webhook + secret diagnostics |
| `plan.json` | 52-week schedule |

## Debugging “menu works but no replies”

The slash menu only proves `setMyCommands` worked. Replies need a **registered webhook**
and a matching `WEBHOOK_SECRET` (server-to-server only — users never type it).

On the VPS:

```bash
# Re-register webhook with the container's .env and probe
docker compose exec bot python debug_webhook.py

# Watch logs while you send /help from the phone
docker logs bible-bot -f

# nginx: are Telegram POSTs hitting /webhook? 200 or 403?
sudo tail -f /var/log/nginx/bible.samtama.lol.access.log
```

Healthy:

| Check | Expect |
|--------|--------|
| `getWebhookInfo.url` | `https://bible.samtama.lol/webhook` |
| `last_error_message` | empty / null |
| Probe **with** secret | HTTP 200 (if secret set) |
| Probe **without** secret | HTTP 403 (if secret set) |
| Logs after `/help` | `webhook_update` then `send_ok` |

If you see many **403** on `/webhook`, Telegram is POSTing but the secret header does not
match `WEBHOOK_SECRET`. Restart the bot so startup re-runs `setWebhook` with the same secret:

```bash
docker compose restart bot
docker logs bible-bot --tail 80
```

Log events: `webhook_register_*`, `webhook_info`, `webhook_secret_rejected`,
`webhook_update`, `send_ok` / `send_failed`.

## Rate limits

bible-api.com ≈ **15 requests / 30 seconds / IP**. Client uses spacing, global budget, 429 backoff, 1h cache, max 6 chapters per `/chapter`.
