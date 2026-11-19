"""Check feeds.

    python -m newsdigest.check_feeds              # every feed in config/sources.yaml
    python -m newsdigest.check_feeds URL [URL..]  # try candidate feed URLs
"""
import re
import sys
from urllib.parse import urljoin

import requests

from .collect import USER_AGENT, fetch_feed
from .config import load_sources


def discover(url: str) -> list[str]:
    """If `url` is a normal web page, look for the RSS/Atom links it advertises."""
    try:
        page = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20).text
    except Exception:
        return []
    found = []
    for tag in re.findall(r"<(?:link|a)\b[^>]*>", page, re.I):
        href = re.search(r'href=["\']([^"\']+)', tag)
        if href and re.search(r"rss|atom|feed", tag, re.I):
            found.append(urljoin(url, href.group(1)))
    return sorted(set(found))[:15]


def main() -> None:
    if len(sys.argv) > 1:
        sources = [{"name": url, "url": url} for url in sys.argv[1:]]
    else:
        sources = load_sources()
    ok, bad = 0, 0
    for source in sources:
        try:
            items = fetch_feed(source)
            newest = max((i["published"] for i in items if i["published"]), default=None)
            when = f"newest {newest:%Y-%m-%d %H:%M}" if newest else "no dates"
            print(f"OK    {source['name']:28s} {len(items):3d} items, {when} | {items[0]['title'][:50]}")
            ok += 1
        except Exception as e:
            print(f"FAIL  {source['name']:28s} {type(e).__name__}: {str(e)[:100]}")
            for link in discover(source["url"]):
                print(f"        possible feed: {link}")
            bad += 1
    print(f"\n{ok} working, {bad} failing")


if __name__ == "__main__":
    main()
