"""Structured logging to stdout (Docker → Grafana Alloy)."""

from __future__ import annotations

import json
from typing import Any


def log_event(msg: str, **fields: Any) -> None:
    payload = {"msg": msg, **fields}
    print(json.dumps(payload, separators=(",", ":"), default=str), flush=True)
