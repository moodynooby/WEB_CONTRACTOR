"""SMTP Email Sender."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from infra.settings import (
    EMAIL_SIGNATURE,
    SMTP_SERVER,
    SMTP_PORT,
    GMAIL_EMAIL,
    GMAIL_PASSWORD,
)
from infra.logging import get_logger
from database.repository import mark_email_sent


class EmailSender:
    """SMTP Email Sender."""

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT
        self.email = GMAIL_EMAIL
        self.password = GMAIL_PASSWORD
        self.email_signature = EMAIL_SIGNATURE

    def log(self, message: str, style: str = "") -> None:
        """Log message with level awareness."""
        if style == "error":
            self.logger.error(message)
        elif style == "warning":
            self.logger.warning(message)
        elif style == "success":
            self.logger.info(message)
        else:
            self.logger.debug(message)

    def send_email(
        self, to_email: str, subject: str, body: str, campaign_id: int | None = None, lead_id: str | None = None
    ) -> bool:
        """Send single email via SMTP"""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email
            msg["To"] = to_email
            msg["Subject"] = subject

            body_with_signature = body + self.email_signature
            msg.attach(MIMEText(body_with_signature, "plain"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)

            if campaign_id:
                mark_email_sent(str(campaign_id), lead_id or "", True)

            return True
        except Exception as e:
            self.log(f"Email send error: {e}", "error")
            if campaign_id:
                mark_email_sent(str(campaign_id), lead_id or "", False, str(e))
            return False
