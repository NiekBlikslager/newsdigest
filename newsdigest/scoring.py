"""Step 3: let a cheap model score every headline against the profile."""
import anthropic
from pydantic import BaseModel

BATCH_SIZE = 60  # headlines per API call


class Score(BaseModel):
    id: str
    score: int            # 0 = irrelevant, 10 = must read
    kind: str             # "achtergrond", "nieuws" or "breaking"
    reason: str           # a few words, for debugging


class ScoreList(BaseModel):
    scores: list[Score]


SYSTEM = """Je beoordeelt nieuwskoppen voor een persoonlijke dagelijkse digest.
Je krijgt het profiel van de lezer en een lijst koppen (met id, bron, categorie, samenvatting).

Geef elke kop een score van 0 tot 10:
- 9-10: niet te missen (echt groot nieuws) of uitzonderlijk sterk achtergrondstuk binnen de hoge prioriteiten
- 7-8: duidelijk relevant en met diepgang (onderzoek, rapport, analyse, trend, belangrijk besluit)
- 5-6: relevant maar vooral dagnieuws, of middel-prioriteit onderwerp
- 0-4: past niet bij het profiel, incident, clickbait, kleine rel, of valt onder "niet opnemen"

Geef "kind": "achtergrond" (analyse/onderzoek/trend), "nieuws" (gewone gebeurtenis) of "breaking" (echt groot).
Waardeer diepgang hoger dan nieuwigheid. Volg de "niet opnemen"-regels strikt.
Verhalen die al in een recente digest stonden (lijst onderaan) krijgen een lage score, tenzij er een belangrijke nieuwe ontwikkeling is.
"reason": maximaal 8 woorden. Geef voor ELK id precies één score."""


def score_items(client: anthropic.Anthropic, groups: list[dict], profile: str,
                recent_titles: list[str], model: str, max_tokens: int) -> dict[str, Score]:
    """Return {item id: Score}. Failed batches are skipped, not fatal."""
    recent = "\n".join(f"- {t}" for t in recent_titles[-80:]) or "(geen)"
    # The profile goes into the cached system prompt; it is the same for every batch.
    system = [{"type": "text", "text": SYSTEM + "\n\n# Profiel van de lezer\n\n" + profile,
               "cache_control": {"type": "ephemeral"}}]
    results: dict[str, Score] = {}

    for start in range(0, len(groups), BATCH_SIZE):
        batch = groups[start:start + BATCH_SIZE]
        lines = []
        for g in batch:
            extra = f" (+{len(g['others'])} andere bronnen)" if g["others"] else ""
            lines.append(f"[{g['id']}] {g['source']} / {g['category']}{extra}\n"
                         f"    {g['title']}\n    {g['summary'][:200]}")
        prompt = ("Recent al in de digest:\n" + recent + "\n\n"
                  "Beoordeel deze koppen:\n\n" + "\n".join(lines))
        try:
            response = client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
                output_format=ScoreList,
            )
        except anthropic.APIStatusError as e:
            print(f"  ! scoring batch {start // BATCH_SIZE + 1} failed: {e.status_code} {e.message}")
            continue
        if response.parsed_output is None:
            print(f"  ! scoring batch {start // BATCH_SIZE + 1}: no parsable output "
                  f"(stop_reason={response.stop_reason})")
            continue
        for s in response.parsed_output.scores:
            results[s.id] = s
        u = response.usage
        print(f"  batch {start // BATCH_SIZE + 1}: {len(batch)} headlines, "
              f"{u.input_tokens} in / {u.output_tokens} out tokens")
    return results
