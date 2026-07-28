#!/usr/bin/env bash
# Host cron entry for the daily push (uses the running bible-bot container).
#
# Crontab example (06:00 Africa/Nairobi — set TZ or use server local time):
#   0 6 * * * /path/to/bible/deploy/run_daily_docker.sh >> /path/to/bible/daily_bread.log 2>&1
#
# Requires: container bible-bot running (docker compose up -d)

set -euo pipefail
cd "$(dirname "$0")"

if ! docker compose ps --status running --services 2>/dev/null | grep -qx bot; then
  echo "bible-bot (service bot) is not running; starting..."
  docker compose up -d bot
  sleep 2
fi

docker compose exec -T bot python daily_bread.py
