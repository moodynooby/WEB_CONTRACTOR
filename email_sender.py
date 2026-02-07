"""Direct SMTP Email Sender"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict
from lead_repository import LeadRepository


class EmailSender:
    """Direct SMTP email sending (no Flask-Mail)"""

    def __init__(self, repo=None, logger=None):
        self.repo = repo or LeadRepository()
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email = os.getenv("GMAIL_EMAIL")
        self.password = os.getenv("GMAIL_PASSWORD")
        self.logger = logger

    def log(self, message: str, style: str = ""):
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
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

            return True

        except Exception as e:
            self.log(f"Email send error: {e}", "error")
            return False

    def send_pending_emails(self, limit: int = 10) -> Dict:
        """Send all pending emails using a single SMTP session"""
        self.log(f"\n{'=' * 60}")
        self.log("EMAIL SENDER: Sending Pending Emails (Session Reuse)")
        self.log(f"{'=' * 60}")

        if not self.email or not self.password:
            self.log("✗ Gmail credentials not configured", "error")
            return {"sent": 0, "failed": 0}

        emails = self.repo.get_pending_emails(limit)
        if not emails:
            self.log("No pending emails to send.", "info")
            return {"sent": 0, "failed": 0}

        self.log(f"Sending {len(emails)} emails...", "info")

        sent = 0
        failed = 0

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)

                for i, email_data in enumerate(emails, 1):
                    try:
                        msg = MIMEMultipart()
                        msg["From"] = self.email
                        msg["To"] = email_data["email"]
                        msg["Subject"] = email_data["subject"]
                        msg.attach(MIMEText(email_data["body"], "plain"))

                        server.send_message(msg)
                        self.repo.mark_email_sent(email_data["campaign_id"], True)
                        sent += 1
                        self.log(f"[{i}/{len(emails)}] Sent to {email_data['email']}", "success")
                    except Exception as e:
                        failed += 1
                        self.repo.mark_email_sent(email_data["campaign_id"], False, error=str(e))
                        self.log(f"[{i}/{len(emails)}] Failed to {email_data['email']}: {e}", "error")
                    
                    time.sleep(1) # Small delay to be polite to SMTP server

        except Exception as e:
            self.log(f"SMTP Session failed: {e}", "error")

        self.log(f"\n{'=' * 60}")
        self.log(f"Email Sending Complete: {sent} sent, {failed} failed", "success")
        self.log(f"{'=' * 60}\n")

        return {"sent": sent, "failed": failed}
