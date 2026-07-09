"""bible-api.com client with global rate limiting and short TTL cache."""

from __future__ import annotations

import html
import re
import threading
import time
from collections import deque
from typing import Any

import requests

from config import (
    BIBLE_API,
    CACHE_TTL_SEC,
    FETCH_MIN_INTERVAL_SEC,
    MAX_CHAPTERS,
    MAX_CHAPTERS_PER_REQUEST,
    MAX_FETCH_RETRIES,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SEC,
    VERSE_RANGE_END,
)

CHAPTER_SUFFIX = re.compile(r"^(.+?)\s+(\d+)(?:-(\d+))?$")
# Single-chapter books: "Jude 1" is ambiguous (verse vs chapter)
SINGLE_CHAPTER_BOOKS = frozenset(
    {
        "obadiah",
        "obad",
        "ob",
        "philemon",
        "phlm",
        "phm",
        "jude",
        "2 john",
        "ii john",
        "2jn",
        "3 john",
        "iii john",
        "3jn",
    }
)


class RateLimiter:
    """Allow up to max_requests per window_sec, plus a minimum spacing."""

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_sec: float = RATE_LIMIT_WINDOW_SEC,
        min_interval: float = FETCH_MIN_INTERVAL_SEC,
    ) -> None:
        self.max_requests = max_requests
        self.window_sec = window_sec
        self.min_interval = min_interval
        self._times: deque[float] = deque()
        self._last: float = 0.0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

    def wait(self) -> None:
        with self._cond:
            while True:
                now = time.monotonic()
                while self._times and now - self._times[0] >= self.window_sec:
                    self._times.popleft()

                wait_window = 0.0
                if len(self._times) >= self.max_requests:
                    wait_window = self.window_sec - (now - self._times[0]) + 0.05

                wait_gap = max(0.0, self.min_interval - (now - self._last))
                delay = max(wait_window, wait_gap)
                if delay <= 0:
                    stamp = time.monotonic()
                    self._times.append(stamp)
                    self._last = stamp
                    self._cond.notify_all()
                    return
                self._cond.wait(timeout=delay)


_limiter = RateLimiter()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def parse_reference(reference: str) -> tuple[str, int | None, int | None]:
    """Parse 'Book N' or 'Book N-M' into (book, start, end). Whole book → end=None."""
    reference = reference.strip()
    match = CHAPTER_SUFFIX.match(reference)
    if match:
        book = match.group(1).strip()
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        return book, start, end
    return reference.strip(), None, None


def _cache_get(key: str) -> dict[str, Any] | None:
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        expires, data = item
        if time.monotonic() > expires:
            del _cache[key]
            return None
        return data


def _cache_set(key: str, data: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + CACHE_TTL_SEC, data)


def api_query(query: str, *, use_cache: bool = True) -> dict[str, Any]:
    """GET a bible-api.com user-input query (spaces allowed; encoded as +)."""
    key = query.strip().lower()
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    url = BIBLE_API + query.replace(" ", "+")
    # Single-chapter books: prefer whole chapter when user asks for "Jude 1"
    if _is_single_chapter_whole_request(query):
        url += (
            ("&" if "?" in url else "?")
            + "single_chapter_book_matching=indifferent"
        )

    last_response: requests.Response | None = None
    for attempt in range(MAX_FETCH_RETRIES):
        _limiter.wait()
        last_response = requests.get(url, timeout=15)
        if last_response.status_code == 429:
            time.sleep(2**attempt)
            continue
        if last_response.status_code == 404:
            data = {"error": "not found"}
            return data
        last_response.raise_for_status()
        data = last_response.json()
        if use_cache and "error" not in data:
            _cache_set(key, data)
        return data

    if last_response is not None:
        last_response.raise_for_status()
    return {"error": "rate limited"}


def _is_single_chapter_whole_request(query: str) -> bool:
    book, start, end = parse_reference(query)
    if start is None or end is None:
        return book.lower() in SINGLE_CHAPTER_BOOKS
    if start != end or start != 1:
        return False
    return book.lower() in SINGLE_CHAPTER_BOOKS


def _needs_verse_range(returned_ref: str, chapter: int) -> bool:
    return re.search(rf"\b{chapter}:\d+\b", returned_ref) is not None


def format_verse_html(data: dict[str, Any]) -> str:
    """Format API JSON into Telegram HTML (verse numbers bold)."""
    verses = data.get("verses")
    if verses:
        parts = []
        for verse in verses:
            text = verse.get("text", "").strip()
            if not text:
                continue
            parts.append(f"<b>{verse['verse']}</b> {html.escape(text)}")
        if parts:
            return "\n".join(parts)

    text = data.get("text", "").strip()
    return html.escape(text) if text else ""


def fetch_chapter(book: str, chapter: int) -> tuple[str, str] | None:
    """Fetch one chapter; return (reference, html_text) or None."""
    query = f"{book} {chapter}"
    data = api_query(query)
    if data.get("error"):
        return None

    returned_ref = data.get("reference", query)
    text = format_verse_html(data)
    if not text:
        return None

    if _needs_verse_range(returned_ref, chapter):
        data = api_query(f"{book} {chapter}:1-{VERSE_RANGE_END}")
        if data.get("error"):
            return None
        returned_ref = data.get("reference", query)
        text = format_verse_html(data)
        if not text:
            return None

    return returned_ref, text


def fetch_verse_reference(reference: str) -> tuple[str, str] | None:
    """Fetch a verse or verse range (must include ':' for verses)."""
    data = api_query(reference.strip())
    if data.get("error"):
        return None
    returned_ref = data.get("reference", reference)
    text = format_verse_html(data)
    if not text:
        return None
    return returned_ref, text


def fetch_bible_text(
    reference: str,
    *,
    max_chapters: int | None = None,
) -> tuple[str | None, list[tuple[str, str]] | None]:
    """
    Resolve a chapter-style reference into a list of (ref, html) chapters.

    max_chapters: cap for interactive use (None = use MAX_CHAPTERS for whole books).
    """
    if not reference:
        return None, None

    book, start, end = parse_reference(reference)
    chapters: list[tuple[str, str]] = []
    cap = max_chapters if max_chapters is not None else MAX_CHAPTERS

    if start is not None and end is not None:
        if end < start:
            start, end = end, start
        span = end - start + 1
        if max_chapters is not None and span > max_chapters:
            return reference, None  # signal caller to show range error
        for chapter in range(start, end + 1):
            try:
                result = fetch_chapter(book, chapter)
            except Exception as e:
                print(f"Fetch warning: {book} {chapter} failed ({e})")
                result = None
            if result is None:
                print(f"Fetch warning: missing {book} {chapter}")
                continue
            chapters.append(result)
    else:
        for chapter in range(1, cap + 1):
            try:
                result = fetch_chapter(book, chapter)
            except Exception as e:
                print(f"Fetch warning: {book} {chapter} failed ({e})")
                result = None
            if result is None:
                break
            chapters.append(result)

    if not chapters:
        return reference, [
            (
                reference,
                html.escape(
                    f"Could not fetch text. Please read {reference} "
                    "on Bible.com or in your app."
                ),
            )
        ]

    return reference, chapters


def chapter_span_too_large(reference: str) -> bool:
    """True if chapter range exceeds MAX_CHAPTERS_PER_REQUEST."""
    _, start, end = parse_reference(reference)
    if start is None or end is None:
        return False
    return abs(end - start) + 1 > MAX_CHAPTERS_PER_REQUEST
