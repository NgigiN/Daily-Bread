#!/usr/bin/env bash
cd "$(dirname "$0")"
./venv/bin/python daily_bread.py >> daily_bread.log 2>&1