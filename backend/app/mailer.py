"""Sending email through an SMTP server (AMG-F-045 sharing, AMG-F-051 reminders).

Configure with environment variables: SMTP_HOST (required), SMTP_PORT (default 587),
SMTP_USER, SMTP_PASSWORD, SMTP_FROM (default: SMTP_USER or ams@localhost) and
SMTP_TLS (default true; uses STARTTLS). For a local test server see scripts/smtp_sink.py.
"""
import os
import smtplib
from email.message import EmailMessage
from typing import Optional


class MailError(Exception):
    """The message could not be sent."""


def configured() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def send(
    to: list[str],
    subject: str,
    body: str,
    attachment: Optional[tuple[bytes, str, str]] = None,
) -> None:
    """Send one email. ``attachment`` is (data, media_type, filename)."""
    host = os.getenv("SMTP_HOST")
    if not host:
        raise MailError("Email is not set up on the server (SMTP_HOST is missing).")
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "minutes@localhost"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)
    if attachment is not None:
        data, media_type, filename = attachment
        maintype, _, subtype = media_type.partition("/")
        message.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)

    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
            if os.getenv("SMTP_TLS", "true").strip().lower() not in {"0", "false", "no", "off"}:
                smtp.starttls()
            if os.getenv("SMTP_USER"):
                smtp.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(f"The mail server could not be reached or refused the message: {exc}") from exc
