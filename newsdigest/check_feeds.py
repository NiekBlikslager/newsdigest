"""Check feeds.

    python -m newsdigest.check_feeds              # every feed in config/sources.yaml
    python -m newsdigest.check_feeds URL [URL..]  # try candidate feed URLs
"""
import sys

from .collect import fetch_feed
from .config import load_sources


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
            bad += 1
    print(f"\n{ok} working, {bad} failing")


if __name__ == "__main__":
    main()
