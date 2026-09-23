"""Envoi du rapport par email (SMTP + STARTTLS). Rien n'est envoyé si la configuration manque."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from scanner.core.config import Secrets
from scanner.core.logging import get_logger

log = get_logger(__name__)


def send_report(secrets: Secrets, subject: str, text: str, html: str) -> bool:
    if not (
        secrets.smtp_host and secrets.smtp_user and secrets.smtp_password and secrets.report_to
    ):
        log.info("email non configuré : rapport non envoyé")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = secrets.smtp_user
    msg["To"] = secrets.report_to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(secrets.smtp_host, secrets.smtp_port, timeout=60) as smtp:
        smtp.starttls()
        smtp.login(secrets.smtp_user, secrets.smtp_password)
        smtp.send_message(msg)
    log.info("rapport envoyé par email", extra={"ctx": {"to": secrets.report_to}})
    return True
