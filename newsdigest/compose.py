"""Step 4: let a stronger model write the digest from the best stories."""
from datetime import datetime

from .render import dutch_date
import anthropic
from pydantic import BaseModel

# Sections in the order they appear in the mail. The model must use these names.
SECTIONS = [
    "Niet te missen",
    "Wereld",
    "Nederland",
    "Economie, wonen en klimaat",
    "Wetenschap en gezondheid",
    "Sport",
    "Tech",
    "Opinie en achtergrond",
    "Het roddelverhaal van de dag",
]


class Link(BaseModel):
    url: str        # must be one of the URLs from the candidate list
    label: str      # e.g. "NOS" or "Guardian: analyse"


class Perspectives(BaseModel):
    progressive: str   # what left/progressive commentators say
    conservative: str  # what right/conservative commentators say
    agreed_facts: str  # what the facts agree on


class Item(BaseModel):
    headline: str
    summary: str                         # 1-3 sentences, own words
    why_it_matters: str | None = None    # 1 sentence of context, optional
    perspectives: Perspectives | None = None
    is_opinion: bool = False
    links: list[Link]
    source_ids: list[str]                # ids of the candidates this item is based on


class Section(BaseModel):
    name: str
    items: list[Item]


class Digest(BaseModel):
    intro: str | None = None   # optional single sentence at the top
    sections: list[Section]


SYSTEM = """Je bent de redacteur van een persoonlijke, dagelijkse nieuwsdigest per e-mail.
Je schrijft in helder, rustig Nederlands, ook als de bron Engels is. Je volgt het profiel
van de lezer (hieronder) nauwkeurig.

Werkwijze:
- Kies uit de kandidaten ongeveer 8 tot 14 items in totaal (ongeveer 5 minuten leestijd).
  Minder mag als er weinig goeds is; nooit opvullen met zwakke items.
- Verschillende kandidaten over hetzelfde verhaal voeg je samen tot één item met meerdere links.
- Diepgang (onderzoek, rapport, analyse, trend) gaat voor dagnieuws. "Niet te missen" alleen
  bij echt groot nieuws; laat die rubriek anders weg.
- Per item 1 tot 3 zinnen in eigen woorden. Geen citaten langer dan een paar woorden.
  Voeg waar het helpt één zin "waarom dit ertoe doet" toe.
- Bij omstreden politieke of geopolitieke kwesties vul je "perspectives" in: de sterkste
  progressieve en de sterkste conservatieve lezing (eerlijk, geen stroman, geen kunstmatige
  balans), en waar de feiten het over eens zijn. Bij niet-omstreden items laat je dit leeg.
  Gebruik je eigen kennis van de gangbare posities alleen als je zeker bent; verzin geen citaten.
- Opiniestukken markeer je met is_opinion = true.
- Rubrieken: gebruik uitsluitend deze namen, laat lege rubrieken weg: {sections}.
  "Het roddelverhaal van de dag" bevat maximaal één item, en alleen als er iets groots speelt.
- Links: gebruik UITSLUITEND URL's uit de kandidatenlijst, letterlijk overgenomen. Zet een
  openbaar toegankelijke bron eerst. Bronnen met [betaalmuur] mogen, maar geef dan zo
  mogelijk ook een open alternatief uit de lijst.
- source_ids: de ids van de kandidaten waarop het item gebaseerd is.
- Je mag met web_fetch spaarzaam de volledige tekst van een openbaar artikel uit de lijst
  lezen als dat echt nodig is voor nuance of context. Verwerk dat in eigen woorden.
- Verhalen die al in een recente digest stonden, neem je alleen op bij een belangrijke
  nieuwe ontwikkeling (en zeg dan wat er nieuw is).
- Als er echt niets relevants is, geef dan een lege lijst sections.

# Profiel van de lezer

{profile}"""


def candidate_block(groups: list[dict], scores: dict) -> str:
    lines = []
    for g in groups:
        s = scores[g["id"]]
        lines.append(f"[{g['id']}] score {s.score} ({s.kind}) | {g['category']}")
        for it in [g, *g["others"]]:
            paywall = " [betaalmuur]" if it["paywall"] else ""
            lines.append(f"    {it['source']}{paywall}: {it['title']}\n"
                         f"      {it['link']}")
        if g["summary"]:
            lines.append(f"    Samenvatting: {g['summary']}")
        lines.append("")
    return "\n".join(lines)


def compose_digest(client: anthropic.Anthropic, groups: list[dict], scores: dict,
                   profile: str, recent_titles: list[str], settings: dict,
                   today: datetime) -> tuple[Digest, dict]:
    """Returns (digest, usage info)."""
    models = settings["models"]
    limits = settings["limits"]
    # str.replace instead of .format, so braces in profile.md can't break anything
    system = (SYSTEM.replace("{sections}", ", ".join(f'"{s}"' for s in SECTIONS))
                    .replace("{profile}", profile))
    recent = "\n".join(f"- {t}" for t in recent_titles[-60:]) or "(geen)"
    user = (f"Vandaag is het {dutch_date(today)} {today.year} (lezer woont in Nederland).\n\n"
            f"Recent al in de digest:\n{recent}\n\n"
            f"# Kandidaten (voorgeselecteerd, hoogste score eerst)\n\n"
            f"{candidate_block(groups, scores)}")

    tools = []
    if limits.get("max_web_fetches", 0) > 0:
        tools.append({"type": "web_fetch_20260209", "name": "web_fetch",
                      "max_uses": limits["max_web_fetches"], "max_content_tokens": 8000})

    messages = [{"role": "user", "content": user}]
    usage = {"input_tokens": 0, "output_tokens": 0}
    # Server tools (web_fetch) can pause a long turn; we then simply resume it.
    for _ in range(4):
        response = client.beta.messages.parse(
            model=models["compose"],
            max_tokens=limits["compose_max_tokens"],
            system=system,
            messages=messages,
            tools=tools,
            output_config={"effort": models.get("compose_effort", "medium")},
            output_format=Digest,
            # If a safety filter declines (rare false positive on news about
            # war/health), the API retries on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        if response.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": user},
                    {"role": "assistant", "content": response.content}]

    if response.stop_reason == "refusal":
        raise RuntimeError("compose model declined the request (refusal)")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("compose model hit max_tokens; raise limits.compose_max_tokens")
    if response.parsed_output is None:
        raise RuntimeError(f"compose model returned no digest (stop_reason={response.stop_reason})")
    usage["model"] = response.model
    return clean_digest(response.parsed_output, groups), usage


def clean_digest(digest: Digest, groups: list[dict]) -> Digest:
    """Safety net: keep only real URLs from the feeds, known sections, in fixed order."""
    known = {}
    for g in groups:
        for it in [g, *g["others"]]:
            known[it["link"]] = it
    sections = []
    for name in SECTIONS:
        items = [i for s in digest.sections if s.name == name for i in s.items]
        for item in items:
            item.links = [l for l in item.links if l.url in known]
        items = [i for i in items if i.links]
        if name == SECTIONS[-1]:
            items = items[:1]
        if items:
            sections.append(Section(name=name, items=items))
    digest.sections = sections
    return digest
