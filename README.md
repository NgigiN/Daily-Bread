# Daily Bread

Telegram bot for a 52-week Bible reading plan: **daily push** (cron) + **interactive commands** (webhook).

Text via [bible-api.com](https://bible-api.com) (WEB), rate-limited for their **15 req / 30s** cap.

## Architecture

```text
Telegram ──HTTPS──► nginx (bible.samtama.lol, certbot)
                         │
                         ▼
              127.0.0.1:5555  (ufw does NOT open 5555)
                         │
                         ▼
              Docker container bible-bot
              (listens 0.0.0.0:5555 inside; host bind is loopback only)

Grafana Alloy (VPS) ──► Grafana Cloud Loki
  {job="docker", container="bible-bot"}
  {job="nginx"}  (site access log)
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

Interactive use is **open** to anyone who starts the bot.  
`TELEGRAM_CHAT_IDS` is only for the **daily cron push**.

---

## Local setup (optional, without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit token / chat ids
python bot_app.py      # or: python daily_bread.py
```

---

## Docker (production shape)

### Image goals

- `python:3.12-slim-bookworm`, non-root user
- Small context via `.dockerignore` (no `venv`, `.git`, logs)
- Layer cache: `requirements.txt` installed before app copy
- Healthcheck without extra packages

### Run on the VPS

```bash
cd /path/to/bible          # PROJECT_PATH
cp .env.example .env       # once; fill secrets
docker compose up -d --build

curl http://127.0.0.1:5555/health
docker logs bible-bot --tail 50
```

**Port rule:** compose publishes **`127.0.0.1:5555:5555` only**.  
Nothing on the public internet should hit 5555; nginx on the host proxies. UFW stays closed for 5555.

Inside the container, the app listens on `0.0.0.0:5555` (required for Docker port mapping). That is **not** public exposure.

### Daily push (host cron + running container)

```bash
chmod +x deploy/run_daily_docker.sh

# crontab -e  (example 06:00 server time)
0 6 * * * /path/to/bible/deploy/run_daily_docker.sh >> /path/to/bible/daily_bread.log 2>&1
```

This runs `docker compose exec -T bot python daily_bread.py` (same image, same `.env`).

---

## nginx site file (name + symlink)

**Config file in repo (exact sites-available name):**

`deploy/nginx/bible.samtama.lol`

**Install:**

```bash
sudo cp /path/to/bible/deploy/nginx/bible.samtama.lol \
  /etc/nginx/sites-available/bible.samtama.lol

sudo ln -sf /etc/nginx/sites-available/bible.samtama.lol \
  /etc/nginx/sites-enabled/bible.samtama.lol

sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d bible.samtama.lol
```

DNS: `bible.samtama.lol` → VPS public IP.

---

## GitHub Actions CI/CD

Workflow: [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)

| Trigger | Action |
|---------|--------|
| Push to **`main`** | SSH → `git pull` → `docker compose build` → `up -d` → health check |

### Secrets (GitHub repo → Settings → Secrets and variables → Actions)

| Secret | Example / notes |
|--------|------------------|
| `SERVER_HOST` | VPS IP or hostname |
| `SERVER_USER` | e.g. `deploy` |
| `SERVER_PORT` | e.g. `22` |
| `SERVER_SSH_KEY` | Full private key PEM (deploy key or user key) |
| `PROJECT_PATH` | Absolute path to this clone on the VPS, e.g. `/home/deploy/opt/bible` |

### One-time VPS prep

1. Clone the repo to `PROJECT_PATH`, install Docker + Compose plugin.
2. Create `.env` there (not in git).
3. Ensure the SSH user can `git fetch`/`pull` (deploy key or HTTPS token) and run `docker` (group membership).
4. Install nginx site + certbot (above).
5. Add cron for daily push.
6. Add GitHub secrets; push to `main`.

CI stays short: **no image build on GitHub runners** — only SSH + cached `docker compose build` on the VPS.

---

## Grafana Cloud (same VPS Alloy stack)

Alloy already scrapes **all** Docker containers ([`logging/ops/alloy/config.alloy`](../logging/ops/alloy/config.alloy)). No Alloy change required.

| Label | Value |
|-------|--------|
| `job` | `docker` |
| `container` | `bible-bot` |
| `service` | `bot` (compose service) |
| `project` | compose project dir name |

**Explore:**

```logql
{job="docker", container="bible-bot"}
{job="docker", container="bible-bot"} | json | msg="request completed" | status != ""
{job="nginx"} |= "bible.samtama.lol"
```

App logs JSON lines: `msg`, `method`, `path`, `status`, `latency_ms`.

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
| `plan.json` | 52-week schedule |

## Rate limits

bible-api.com ≈ **15 requests / 30 seconds / IP**. Client uses spacing, global budget, 429 backoff, 1h cache, max 6 chapters per `/chapter`.
