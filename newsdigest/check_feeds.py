"""Check every feed in config/sources.yaml:  python -m newsdigest.check_feeds"""
from .collect import fetch_feed
from .config import load_sources


def main() -> None:
    ok, bad = 0, 0
    for source in load_sources():
        try:
            items = fetch_feed(source)
            newest = max((i["published"] for i in items if i["published"]), default=None)
            print(f"OK    {source['name']:28s} {len(items):3d} items, newest {newest:%Y-%m-%d %H:%M}"
                  if newest else f"OK    {source['name']:28s} {len(items):3d} items, no dates")
            ok += 1
        except Exception as e:
            print(f"FAIL  {source['name']:28s} {type(e).__name__}: {str(e)[:100]}")
            bad += 1
    print(f"\n{ok} working, {bad} failing")


if __name__ == "__main__":
    main()
