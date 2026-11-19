"""Entry point.

    python -m newsdigest --collect-only   # only fetch + group feeds (no API key needed)
    python -m newsdigest --dry-run        # full run, write output/digest.html, no mail
    python -m newsdigest --test           # full run, send one real mail marked [TEST]
    python -m newsdigest                  # scheduled run (used by GitHub Actions)
"""
import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from itertools import zip_longest
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
    hh, mm = map(int, settings["schedule"]["send_at"].split(":"))
    send_at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < send_at - timedelta(minutes=45):
        return f"too early ({now:%H:%M}, digest is sent at {send_at:%H:%M})"
    if now.hour >= settings["schedule"].get("latest_send_hour", 10):
        return f"too late ({now:%H:%M})"
    return None


def wait_until_send_time(settings: dict, tz: ZoneInfo) -> None:
    hh, mm = map(int, settings["schedule"]["send_at"].split(":"))
    now = datetime.now(tz)
    send_at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < send_at:
        seconds = (send_at - now).total_seconds()
        print(f"Waiting {seconds / 60:.0f} min until {send_at:%H:%M} to send.")
        time.sleep(seconds)


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

    if digest is None or not digest.sections:
        html, text = render.render_simple(
            "Vandaag niets bijzonders",
            "Er was vandaag niets dat goed bij je profiel past. Morgen weer.\n\n" + footer)
    else:
        paywalled = {it["link"] for g in best for it in [g, *g["others"]] if it["paywall"]}
        html = render.render_html(digest, now, paywalled, footer)
        text = render.render_text(digest, now, paywalled, footer)

    # 5. Output / send
    if mode == "dry-run":
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "digest.html").write_text(html, encoding="utf-8")
        (OUTPUT_DIR / "digest.txt").write_text(text, encoding="utf-8")
        print("\n" + text + f"\n\nWritten to {OUTPUT_DIR / 'digest.html'}")
        return 0

    if mode == "scheduled":
        wait_until_send_time(settings, tz)
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
    args = parser.parse_args()
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
