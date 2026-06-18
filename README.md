# Daily Bread

If I'm so attached to my phone, I may just as well read the whole Bible in 1 year while I'm at it.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your bot token from [@BotFather](https://t.me/BotFather).

## Add recipients

Each person must open your bot and tap **Start**.

Then run the following command to get their chat ids:

```bash
python discover_chats.py
```

Copy the chat IDs into `TELEGRAM_CHAT_IDS` in `.env` (comma-separated for multiple people).

## Run

```bash
python daily_bread.py
```

## Files

- `daily_bread.py` — fetches today's passage and sends it
- `discover_chats.py` — lists chat IDs from people who started the bot
- `plan.json` — the 52-week reading schedule
- `.env` — your bot token and chat IDs (not committed to git)

Text is fetched from [bible-api.com](https://bible-api.com) one chapter at a time.
