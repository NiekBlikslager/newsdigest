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


def render_html(digest, dt, paywalled: set[str], footer: str = "") -> str:
    p = []
    p.append('<!doctype html><html lang="nl"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width, initial-scale=1">'
             f"<title>{escape(subject(dt))}</title></head>")
    p.append('<body style="margin:0;padding:0;background:#f4f4f2;">'
             '<div style="max-width:640px;margin:0 auto;padding:24px 16px;'
             'font-family:Georgia,\'Times New Roman\',serif;color:#1a1a1a;'
             'font-size:16px;line-height:1.5;">')
    p.append(f'<h1 style="font-size:24px;margin:0 0 4px;">Je digest</h1>'
             f'<div style="color:#666;font-size:14px;margin-bottom:16px;">{escape(dutch_date(dt))}</div>')
    if digest.intro:
        p.append(f'<p style="margin:0 0 16px;">{escape(digest.intro)}</p>')

    for section in digest.sections:
        p.append('<h2 style="font-family:Helvetica,Arial,sans-serif;font-size:13px;'
                 'letter-spacing:.08em;text-transform:uppercase;color:#8a3b12;'
                 'border-top:2px solid #1a1a1a;padding-top:8px;margin:28px 0 8px;">'
                 f"{escape(section.name)}</h2>")
        for item in section.items:
            badge = (' <span style="font-family:Helvetica,Arial,sans-serif;font-size:11px;'
                     'background:#eee;color:#555;padding:1px 6px;border-radius:3px;'
                     'vertical-align:middle;">OPINIE</span>') if item.is_opinion else ""
            p.append(f'<div style="margin:0 0 18px;"><div style="font-weight:bold;font-size:17px;">'
                     f"{escape(item.headline)}{badge}</div>")
            p.append(f'<div style="margin-top:4px;">{escape(item.summary)}</div>')
            if item.why_it_matters:
                p.append(f'<div style="margin-top:4px;color:#444;"><i>Waarom het ertoe doet:</i> '
                         f"{escape(item.why_it_matters)}</div>")
            if item.perspectives:
                pv = item.perspectives
                p.append('<div style="margin-top:6px;padding:6px 10px;background:#fff;'
                         'border-left:3px solid #ccc;font-size:15px;">'
                         f"<b>Progressief:</b> {escape(pv.progressive)}<br>"
                         f"<b>Conservatief:</b> {escape(pv.conservative)}<br>"
                         f"<b>Waar de feiten het over eens zijn:</b> {escape(pv.agreed_facts)}</div>")
            links = " · ".join(f'<a href="{escape(l.url)}" style="color:#1a5fb4;">'
                               f"{escape(link_label(l, paywalled))}</a>" for l in item.links)
            p.append('<div style="margin-top:4px;font-family:Helvetica,Arial,sans-serif;'
                     f'font-size:13px;color:#666;">Verder lezen: {links}</div></div>')

    if footer:
        p.append('<div style="margin-top:32px;font-family:Helvetica,Arial,sans-serif;'
                 f'font-size:12px;color:#888;">{escape(footer)}</div>')
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
