"""SMTP Email Sender - Simplified single-threaded design

Uses direct SMTP with context manager for efficient connection handling.
"""

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, Optional

from core.db_peewee import init_db, mark_email_sent


class EmailSender:
    """SMTP Email Sender - simplified without connection pooling"""

    def __init__(
        self,
        logger: Optional[Callable] = None,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email = email or __import__("os").getenv("GMAIL_EMAIL")
        self.password = password or __import__("os").getenv("GMAIL_PASSWORD")
        self.logger = logger
        self.email_signature = self._load_email_signature()

        init_db()

    def _load_email_signature(self) -> str:
        """Load email signature from config file"""
        try:
            with open("config/email_prompts.json", "r") as f:
                config = json.load(f)
                sig_config = config.get("email_signature", {})
                template = sig_config.get("template", "\n\nBest regards,\nManas Doshi")
                return template.format(
                    name=sig_config.get("name", "Manas Doshi"),
                    company=sig_config.get("company", "Future Forwards"),
                    website=sig_config.get(
                        "website", "https://man27.netlify.app/services"
                    ),
                )
        except Exception:
            return "\n\nBest regards,\nManas Doshi,\nFuture Forwards - https://man27.netlify.app/services"

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def send_email(self, to_email: str, subject: str, body: str, campaign_id: int = None) -> bool:
        """Send single email via SMTP"""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)

            if campaign_id:
                mark_email_sent(campaign_id, True)

            return True
        except Exception as e:
            self.log(f"Email send error: {e}", "error")
            if campaign_id:
                mark_email_sent(campaign_id, False, str(e))
            return False
