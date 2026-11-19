"""Remember what was sent, so stories don't come back day after day.

state/state.json is committed back to the repository by the GitHub workflow.
The 'digests' list keeps item ids per day; a later feedback feature
(thumbs up/down per item) can link to those ids.
"""
import json
from datetime import date, timedelta

from .config import STATE_FILE


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_sent_date": None, "seen": [], "digests": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def record_digest(state: dict, today: date, digest, groups: list[dict], history_days: int) -> None:
    by_id = {g["id"]: g for g in groups}
    items = []
    for section in digest.sections:
        for item in section.items:
            items.append({"headline": item.headline, "section": section.name,
                          "source_ids": item.source_ids,
                          "links": [l.url for l in item.links]})
            # Mark the candidate stories (and all their links) as seen.
            for sid in item.source_ids:
                g = by_id.get(sid)
                if g:
                    for it in [g, *g["others"]]:
                        state["seen"].append({"date": today.isoformat(), "title": it["title"],
                                              "link": it["link"]})
            for url in [l.url for l in item.links]:
                state["seen"].append({"date": today.isoformat(), "title": item.headline, "link": url})
    state["digests"].append({"date": today.isoformat(), "items": items})
    state["last_sent_date"] = today.isoformat()

    cutoff = (today - timedelta(days=history_days)).isoformat()
    state["seen"] = [s for s in state["seen"] if s["date"] >= cutoff]
    state["digests"] = [d for d in state["digests"] if d["date"] >= cutoff]


def recent_titles(state: dict) -> list[str]:
    return [i["headline"] for d in state["digests"] for i in d["items"]]
