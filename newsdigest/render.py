"""Turn a Digest into a simple HTML mail and a plain-text version."""
from html import escape

DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
          "augustus", "september", "oktober", "november", "december"]


def dutch_date(dt) -> str:
    """e.g. 'donderdag 19 november'"""
    return f"{DAYS[dt.weekday()]} {dt.day} {MONTHS[dt.month - 1]}"


def subject(dt, test: bool = False) -> str:
    return ("[TEST] " if test else "") + f"Je digest, {dutch_date(dt)}"


def link_label(link, paywalled: set[str]) -> str:
    return link.label + (" (betaalmuur)" if link.url in paywalled else "")


# Colours and fonts in one place, so the look is easy to tweak.
INK = "#16181d"        # main text
MUTED = "#6b7280"      # dates, links line, footer
ACCENT = "#c2410c"     # section labels
LINK = "#1d4ed8"
CARD = "#f5f5f4"       # background of the perspectives block
RULE = "#e7e5e4"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# Only clients that support it (Apple Mail, iOS) use this; the inline styles are the base.
DARK_MODE_CSS = f"""
:root {{ color-scheme: light dark; supported-color-schemes: light dark; }}
@media (prefers-color-scheme: dark) {{
  .bg {{ background:#111214 !important; }}
  .ink {{ color:#ececec !important; }}
  .muted {{ color:#9ca3af !important; }}
  .card {{ background:#1c1d21 !important; }}
  .rule {{ border-color:#2a2b30 !important; }}
  a {{ color:#93b4ff !important; }}
}}
"""


def render_html(digest, dt, paywalled: set[str], footer: str = "") -> str:
    p = []
    preheader = digest.intro or "Je dagelijkse digest"
    p.append('<!doctype html><html lang="nl"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width, initial-scale=1">'
             '<meta name="color-scheme" content="light dark">'
             '<meta name="supported-color-schemes" content="light dark">'
             f"<title>{escape(subject(dt))}</title><style>{DARK_MODE_CSS}</style></head>")
    p.append(f'<body class="bg" style="margin:0;padding:0;background:#ffffff;">')
    # Hidden preview text shown next to the subject in the inbox
    p.append(f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
             f"{escape(preheader)}</div>")
    p.append(f'<div class="ink" style="max-width:600px;margin:0 auto;padding:28px 20px 40px;'
             f'font-family:{SANS};color:{INK};font-size:17px;line-height:1.6;'
             '-webkit-text-size-adjust:100%;">')

    # Header
    p.append(f'<div class="muted" style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;'
             f'color:{MUTED};font-weight:600;">Je digest</div>'
             f'<div style="font-size:28px;line-height:1.2;font-weight:700;letter-spacing:-.01em;'
             f'margin:4px 0 0;">{escape(dutch_date(dt).capitalize())}</div>')
    if digest.intro:
        p.append(f'<p class="muted" style="margin:12px 0 0;font-size:16px;color:{MUTED};">'
                 f"{escape(digest.intro)}</p>")

    for section in digest.sections:
        p.append(f'<div class="rule" style="border-top:1px solid {RULE};margin:32px 0 0;'
                 f'padding-top:14px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;'
                 f'font-weight:700;color:{ACCENT};">{escape(section.name)}</div>')
        for n, item in enumerate(section.items):
            top = "14px" if n == 0 else "28px"
            badge = (f'<span class="muted" style="font-size:11px;letter-spacing:.1em;font-weight:700;'
                     f'color:{MUTED};border:1px solid {RULE};border-radius:4px;padding:1px 5px;'
                     f'margin-right:6px;vertical-align:2px;">OPINIE</span>') if item.is_opinion else ""
            p.append(f'<div style="margin-top:{top};">'
                     f'<div style="font-size:20px;line-height:1.3;font-weight:700;letter-spacing:-.005em;">'
                     f"{badge}{escape(item.headline)}</div>")
            p.append(f'<p style="margin:8px 0 0;">{escape(item.summary)}</p>')
            if item.why_it_matters:
                p.append(f'<p style="margin:8px 0 0;"><b>Waarom het ertoe doet.</b> '
                         f"{escape(item.why_it_matters)}</p>")
            if item.perspectives:
                pv = item.perspectives
                row = ('<div style="margin-top:{m};"><span style="font-size:12px;letter-spacing:.08em;'
                       'text-transform:uppercase;font-weight:700;color:{c};">{t}</span><br>{v}</div>')
                p.append(f'<div class="card" style="margin-top:12px;padding:12px 14px;background:{CARD};'
                         'border-radius:10px;font-size:15px;line-height:1.5;">'
                         + row.format(m="0", c="#be123c", t="Progressief", v=escape(pv.progressive))
                         + row.format(m="10px", c="#1d4ed8", t="Conservatief", v=escape(pv.conservative))
                         + row.format(m="10px", c=MUTED, t="Feiten", v=escape(pv.agreed_facts))
                         + "</div>")
            links = []
            for l in item.links:
                paywall = (f' <span class="muted" style="color:{MUTED};">(betaalmuur)</span>'
                           if l.url in paywalled else "")
                links.append(f'<a href="{escape(l.url)}" style="color:{LINK};text-decoration:none;">'
                             f"{escape(l.label)}</a>{paywall}")
            p.append(f'<div class="muted" style="margin-top:8px;font-size:14px;line-height:1.7;color:{MUTED};">'
                     f'Lees verder: {" &nbsp;·&nbsp; ".join(links)}</div></div>')

    if footer:
        p.append(f'<div class="muted rule" style="margin-top:40px;padding-top:14px;border-top:1px solid {RULE};'
                 f'font-size:12px;color:{MUTED};">{escape(footer)}</div>')
    p.append("</div></body></html>")
    return "\n".join(p)


def render_text(digest, dt, paywalled: set[str], footer: str = "") -> str:
    out = [f"JE DIGEST - {dutch_date(dt)}", ""]
    if digest.intro:
        out += [digest.intro, ""]
    for section in digest.sections:
        out += [section.name.upper(), "-" * len(section.name), ""]
        for item in section.items:
            out.append(("[OPINIE] " if item.is_opinion else "") + item.headline)
            out.append(item.summary)
            if item.why_it_matters:
                out.append(f"Waarom het ertoe doet: {item.why_it_matters}")
            if item.perspectives:
                pv = item.perspectives
                out.append(f"  Progressief: {pv.progressive}")
                out.append(f"  Conservatief: {pv.conservative}")
                out.append(f"  Feiten: {pv.agreed_facts}")
            for l in item.links:
                out.append(f"  > {link_label(l, paywalled)}: {l.url}")
            out.append("")
    if footer:
        out += ["--", footer]
    return "\n".join(out)


def render_simple(title: str, message: str) -> tuple[str, str]:
    """For the 'nothing relevant today' mail and error mails."""
    html = ('<!doctype html><html><body style="font-family:Helvetica,Arial,sans-serif;'
            'max-width:640px;margin:0 auto;padding:24px 16px;">'
            f"<h2>{escape(title)}</h2><pre style=\"white-space:pre-wrap;\">{escape(message)}</pre>"
            "</body></html>")
    return html, f"{title}\n\n{message}"
