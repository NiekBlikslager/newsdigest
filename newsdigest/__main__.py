"""Entry point.

    python -m newsdigest --collect-only   # only fetch + group feeds (no API key needed)
    python -m newsdigest --dry-run        # full run, write output/digest.html, no mail
    python -m newsdigest --test           # full run, send one real mail marked [TEST]
    python -m newsdigest --send-saved output/digest.json   # re-mail a saved dry-run, no API calls
    python -m newsdigest                  # scheduled run (used by GitHub Actions)
"""
import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from itertools import zip_longest
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

from . import render
from .collect import collect
from .compose import compose_digest
from .config import OUTPUT_DIR, load_profile, load_settings, load_sources
from .dedupe import drop_already_sent, group_stories
from .mailer import send_mail
from .scoring import score_items
from .state import load_state, recent_titles, record_digest, save_state


def round_robin(groups: list[dict], limit: int) -> list[dict]:
    """Take at most `limit` stories, alternating between sources so no feed dominates."""
    by_source: dict[str, list] = {}
    for g in groups:
        by_source.setdefault(g["source"], []).append(g)
    mixed = [g for row in zip_longest(*by_source.values()) for g in row if g]
    return mixed[:limit]


def check_schedule(settings: dict, state: dict, now: datetime) -> str | None:
    """Return a reason to skip this scheduled run, or None to go ahead."""
    if state.get("last_sent_date") == now.date().isoformat():
        return "digest already sent today"
    hh, mm = map(int, settings["schedule"]["start_at"].split(":"))
    start_at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < start_at - timedelta(minutes=30):
        return f"too early ({now:%H:%M}, the digest run starts at {start_at:%H:%M})"
    if now.hour >= settings["schedule"].get("latest_send_hour", 10):
        return f"too late ({now:%H:%M})"
    return None


def add_entertainment(best: list[dict], groups: list[dict], scores: dict, n: int = 3) -> list[dict]:
    """Make sure the compose model always has a few entertainment stories to choose from,
    even if they scored low (the profile asks for exactly one every day)."""
    have = {g["id"] for g in best}
    fun = sorted((g for g in groups if g["category"] == "entertainment" and g["id"] in scores
                  and g["id"] not in have),
                 key=lambda g: scores[g["id"]].score, reverse=True)
    already = sum(1 for g in best if g["category"] == "entertainment")
    return best + fun[: max(0, n - already)]


def send_saved(path: str) -> int:
    """Re-send a saved digest (output/digest.json from a dry-run) as a [TEST] mail.
    Makes no Claude API calls, so it costs nothing."""
    from .compose import Digest
    settings = load_settings()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    digest = Digest.model_validate(data["digest"])
    day = datetime.fromisoformat(data["date"])
    paywalled = set(data.get("paywalled", []))
    html = render.render_html(digest, day, paywalled, data.get("footer", ""))
    text = render.render_text(digest, day, paywalled, data.get("footer", ""))
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "digest.html").write_text(html, encoding="utf-8")
    send_mail(settings, render.subject(day, test=True), html, text)
    return 0


def run(mode: str) -> int:
    settings = load_settings()
    tz = ZoneInfo(settings["schedule"]["timezone"])
    now = datetime.now(tz)
    state = load_state()

    if mode == "scheduled":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Skipping: ANTHROPIC_API_KEY is not set yet (see README).")
            return 0
        reason = check_schedule(settings, state, now)
        if reason:
            print(f"Skipping: {reason}.")
            return 0

    # 1. Collect
    hours = settings["window"]["monday_hours"] if now.weekday() == 0 else settings["window"]["hours"]
    sources = load_sources()
    print(f"Collecting {len(sources)} feeds (last {hours} hours)...")
    items, failed = collect(sources, hours)

    # 2. Group duplicates, drop what was already sent
    groups = drop_already_sent(group_stories(items), state["seen"])
    print(f"{len(items)} items -> {len(groups)} unique new stories. Failed feeds: {failed or 'none'}")
    if mode == "collect-only":
        for g in groups:
            extra = f"  (+ {', '.join(o['source'] for o in g['others'])})" if g["others"] else ""
            print(f"- [{g['source']}] {g['title']}{extra}")
        return 0
    if len(failed) > len(sources) / 2:
        raise RuntimeError(f"more than half of the feeds failed: {', '.join(failed)}")

    limits = settings["limits"]
    groups = round_robin(groups, limits["max_headlines_to_score"])
    profile = load_profile()
    recent = recent_titles(state)
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    # 3. Score with the cheap model
    print(f"Scoring {len(groups)} stories with {settings['models']['select']}...")
    scores = score_items(client, groups, profile, recent, settings["models"]["select"],
                         limits["select_max_tokens"])
    if groups and not scores:
        raise RuntimeError("scoring failed for all batches")
    best = sorted((g for g in groups if g["id"] in scores and scores[g["id"]].score >= limits["min_score"]),
                  key=lambda g: scores[g["id"]].score, reverse=True)[: limits["max_items_to_compose"]]
    print(f"{len(best)} stories scored >= {limits['min_score']}.")
    best = add_entertainment(best, groups, scores)

    footer = f"Samengesteld uit {len(groups)} verhalen uit {len(sources) - len(failed)} bronnen."
    if failed:
        footer += f" Niet bereikbaar vandaag: {', '.join(failed)}."
    subject = render.subject(now, test=(mode == "test"))

    # 4. Compose with the stronger model
    digest = None
    if best:
        print(f"Composing with {settings['models']['compose']}...")
        digest, usage = compose_digest(client, best, scores, profile, recent, settings, now)
        print(f"  compose usage: {usage}")

    paywalled = {it["link"] for g in best for it in [g, *g["others"]] if it["paywall"]}
    if digest is None or not digest.sections:
        html, text = render.render_simple(
            "Vandaag niets bijzonders",
            "Er was vandaag niets dat goed bij je profiel past. Morgen weer.\n\n" + footer)
    else:
        html = render.render_html(digest, now, paywalled, footer)
        text = render.render_text(digest, now, paywalled, footer)

    # 5. Output / send
    if mode == "dry-run":
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "digest.html").write_text(html, encoding="utf-8")
        (OUTPUT_DIR / "digest.txt").write_text(text, encoding="utf-8")
        if digest and digest.sections:
            # Saved so it can be mailed later without new API calls (--send-saved).
            (OUTPUT_DIR / "digest.json").write_text(json.dumps({
                "date": now.date().isoformat(), "digest": digest.model_dump(),
                "paywalled": sorted(paywalled), "footer": footer,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n" + text + f"\n\nWritten to {OUTPUT_DIR / 'digest.html'}")
        return 0

    send_mail(settings, subject, html, text)
    if mode == "scheduled":
        if digest:
            record_digest(state, now.date(), digest, best, settings.get("history_days", 14))
        else:
            state["last_sent_date"] = now.date().isoformat()
        save_state(state)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal daily news digest")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="no mail, write output/digest.html")
    group.add_argument("--test", action="store_true", help="send one real [TEST] mail now")
    group.add_argument("--collect-only", action="store_true", help="only fetch and group feeds")
    group.add_argument("--send-saved", metavar="JSON",
                       help="mail a saved digest.json as [TEST], without API calls")
    args = parser.parse_args()
    if args.send_saved:
        sys.exit(send_saved(args.send_saved))
    mode = ("dry-run" if args.dry_run else "test" if args.test
            else "collect-only" if args.collect_only else "scheduled")

    try:
        sys.exit(run(mode))
    except Exception:
        error = traceback.format_exc()
        print(error, file=sys.stderr)
        if mode in ("scheduled", "test"):
            try:
                html, text = render.render_simple("Nieuwsdigest mislukt", error)
                send_mail(load_settings(), "Nieuwsdigest: run mislukt", html, text)
            except Exception as mail_error:
                print(f"Could not send error mail either: {mail_error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
