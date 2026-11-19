"""Step 2: group near-duplicate stories and drop stories we already sent."""
import re

# Short words that say nothing about the story itself (Dutch + English).
STOPWORDS = set("""
de het een en of van in op aan voor met over na bij uit door is zijn wordt worden
dat die dit deze er om te tot als ook niet nog maar naar hoe wat wie waarom
the a an and or of in on at to for with from by is are was were be has have
that this it its as after over into new says say will can not how why what who
""".split())


def words(title: str) -> set[str]:
    tokens = re.findall(r"[a-zà-ÿ0-9]+", title.lower())
    return {t for t in tokens if t not in STOPWORDS and len(t) > 2}


def similar(a: set[str], b: set[str], threshold: float = 0.5) -> bool:
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= threshold and len(a & b) >= 2


def group_stories(items: list[dict]) -> list[dict]:
    """Merge items about the same story. Each group keeps all its sources.

    This is a cheap word-overlap check; it mostly catches the same story from
    several feeds of one outlet or from outlets in the same language. The
    compose model merges remaining (e.g. Dutch vs English) duplicates.
    """
    groups: list[dict] = []
    seen_links = set()
    for item in items:
        if item["link"] in seen_links:
            continue
        seen_links.add(item["link"])
        w = words(item["title"])
        for g in groups:
            if similar(w, g["_words"]):
                g["others"].append(item)
                break
        else:
            groups.append({**item, "others": [], "_words": w})
    for g in groups:
        del g["_words"]
    return groups


def drop_already_sent(groups: list[dict], seen: list[dict]) -> list[dict]:
    """Remove stories whose link (or a near-identical title) was in a recent digest."""
    seen_links = {s["link"] for s in seen}
    seen_words = [words(s["title"]) for s in seen]
    result = []
    for g in groups:
        links = {g["link"], *(o["link"] for o in g["others"])}
        if links & seen_links:
            continue
        if any(similar(words(g["title"]), sw, 0.8) for sw in seen_words):
            continue
        result.append(g)
    return result
