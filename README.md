# Daily Bread

If I'm so attached to my phone, I may just as well read the whole Bible in 1 year while I'm at it.

Two ways to use the bot:

1. **Daily push (cron)** — `daily_bread.py` sends today's 52-week plan reading to `TELEGRAM_CHAT_IDS`.
2. **Interactive commands (webhook)** — anyone who starts the bot can use `/today`, `/verse`, `/chapter`, `/day`, etc.

Text is fetched from [bible-api.com](https://bible-api.com) (default WEB translation), rate-limited to stay within **15 requests / 30 seconds** per IP.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your bot token from [@BotFather](https://t.me/BotFather).

### Daily push recipients

Each person must open your bot and tap **Start**, then either:

- Run `python discover_chats.py` **before** the webhook is set (uses `getUpdates`), or
- Put their chat ID in `TELEGRAM_CHAT_IDS` manually.

```bash
python discover_chats.py
```

Copy chat IDs into `TELEGRAM_CHAT_IDS` (comma-separated). Interactive commands work for **anyone**; the list is only for the daily cron push.

## Commands

| Command | Example | What it does |
|---------|---------|----------------|
| `/start` | `/start` | Welcome + short list |
| `/help` | `/help` | Full help |
| `/today` | `/today` | Today's plan reading (Africa/Nairobi) |
| `/day` | `/day 17 may` | Plan reading for that date in the **current year** |
| `/verse` | `/verse John 3:16` | Verse or range (`Jn 3:16-17`, `Matt 25:31-33`) |
| `/chapter` | `/chapter John 3` | Full chapter or range (`Rom 1-2`, max 6 chapters) |

## Run locally

### Daily push (unchanged)

```bash
python daily_bread.py
# or
./run_daily.sh
```

### Interactive bot

```bash
# Uses APP_HOST / APP_PORT from .env (default 127.0.0.1:5555)
python bot_app.py
# or
uvicorn bot_app:app --host 127.0.0.1 --port 5555
```

Health check: `curl http://127.0.0.1:5555/health`

## Deploy (nginx + certbot + systemd)

Domain: **`bible.samtama.lol`** → reverse proxy to **`127.0.0.1:5555`** (port 8000 is reserved for other services).

1. Point DNS A/AAAA for `bible.samtama.lol` at the server.
2. Copy and enable nginx:

   ```bash
   sudo cp deploy/nginx-bible.samtama.lol.conf /etc/nginx/sites-available/bible.samtama.lol
   sudo ln -sf /etc/nginx/sites-available/bible.samtama.lol /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```

3. TLS:

   ```bash
   sudo certbot --nginx -d bible.samtama.lol
   ```

4. Install the app service (edit paths/User in the unit if needed):

   ```bash
   sudo cp deploy/bible-bot.service /etc/systemd/system/bible-bot.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now bible-bot
   ```

5. Set in `.env`:

   ```env
   WEBHOOK_URL=https://bible.samtama.lol/webhook
   WEBHOOK_SECRET=some-long-random-string
   APP_PORT=5555
   ```

   On startup the app calls `setMyCommands` and `setWebhook` when `WEBHOOK_URL` is set.

6. Confirm:

   ```bash
   curl https://bible.samtama.lol/health
   # In Telegram: /start, /help, /verse John 3:16
   ```

**Note:** While a webhook is active, Telegram will not deliver updates to `getUpdates`, so `discover_chats.py` will not see new chats until the webhook is removed.

## Project layout

| Path | Role |
|------|------|
| `daily_bread.py` | Cron / one-shot daily push |
| `bot_app.py` | FastAPI webhook server |
| `commands.py` | Command parse + handlers |
| `bible_client.py` | bible-api.com client, rate limit, cache |
| `plan_reader.py` | `plan.json` lookup by date |
| `formatting.py` | Telegram HTML messages |
| `telegram_client.py` | sendMessage, setWebhook, setMyCommands |
| `config.py` | Env + constants |
| `plan.json` | 52-week schedule |
| `deploy/` | nginx + systemd templates |

## Rate limits

bible-api.com allows about **15 requests every 30 seconds** per IP. This project:

- spaces requests (≥ 0.5s) and caps concurrent budget (~14 / 30s),
- retries on HTTP 429,
- caches successful lookups for 1 hour,
- limits `/chapter` ranges to **6** chapters.

Cron and the webhook share the same public IP if they run on the same host.

## Files (legacy helpers)

- `discover_chats.py` — list chat IDs via `getUpdates` (offline webhook)
- `run_daily.sh` — cron wrapper for `daily_bread.py`
