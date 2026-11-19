"""Step 5: send the mail via Resend (default) or SMTP."""
import os
import smtplib
from email.message import EmailMessage

import requests


def recipient(settings: dict) -> str:
    return os.environ.get("DIGEST_TO") or settings["email"]["to"]


def send_mail(settings: dict, subject: str, html: str, text: str) -> None:
    to = recipient(settings)
    sender = os.environ.get("DIGEST_FROM") or settings["email"]["from"]
    provider = settings["email"].get("provider", "resend")

    if provider == "resend":
        key = os.environ.get("RESEND_API_KEY")
        if not key:
            raise RuntimeError("RESEND_API_KEY is not set")
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json={"from": sender, "to": [to], "subject": subject, "html": html, "text": text},
            timeout=30,
        )
        if r.status_code >= 300:
            raise RuntimeError(f"Resend error {r.status_code}: {r.text[:300]}")

    elif provider == "smtp":
        # e.g. Gmail: SMTP_HOST=smtp.gmail.com, SMTP_USER=you@gmail.com, SMTP_PASSWORD=app password
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = os.environ.get("SMTP_USER", sender)
        msg["To"] = to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        port = int(os.environ.get("SMTP_PORT", "465"))
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        raise RuntimeError(f"unknown email provider: {provider}")
    print(f"  mail sent to {to}: {subject}")
