"""Step 1: fetch RSS feeds and keep only recent items."""
import calendar
import hashlib
import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import requests

USER_AGENT = "Mozilla/5.0 (compatible; personal-newsdigest/1.0)"
TIMEOUT = 30  # seconds per feed


def clean_text(text: str, max_len: int = 300) -> str:
    """Strip HTML tags and whitespace from a feed summary and shorten it."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ("…" if len(text) > max_len else "")


def item_id(link: str, title: str) -> str:
    """Short stable id for an item (also usable later for thumbs up/down feedback)."""
    return hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:10]


def entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def fetch_feed(source: dict) -> list[dict]:
    """Fetch one feed. Raises on network/parse errors; caller handles that."""
    resp = requests.get(source["url"], headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if not feed.entries:
        raise ValueError("feed has no entries")
    items = []
    for entry in feed.entries[: source.get("max_items", 25)]:
        title = clean_text(entry.get("title", ""), 200)
        link = entry.get("link", "")
        if not title or not link:
            continue
        items.append({
            "id": item_id(link, title),
            "title": title,
            "link": link,
            "source": source["name"],
            "category": source.get("category", ""),
            "paywall": bool(source.get("paywall", False)),
            "published": entry_time(entry),
            "summary": clean_text(entry.get("summary", "")),
        })
    return items


def collect(sources: list[dict], hours: int) -> tuple[list[dict], list[str]]:
    """Fetch all feeds in parallel. Returns (recent items, names of failed sources)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items, failed = [], []

    def safe_fetch(source):
        try:
            return source, fetch_feed(source), None
        except Exception as e:  # one broken feed must not stop the run
            return source, [], e

    with ThreadPoolExecutor(max_workers=12) as pool:
        for source, fetched, error in pool.map(safe_fetch, sources):
            if error:
                print(f"  ! {source['name']}: {type(error).__name__}: {error}")
                failed.append(source["name"])
                continue
            # Items without a date are kept (some feeds omit dates).
            recent = [i for i in fetched if i["published"] is None or i["published"] >= cutoff]
            print(f"  {source['name']}: {len(recent)} recent / {len(fetched)}")
            items.extend(recent)
    return items, failed
