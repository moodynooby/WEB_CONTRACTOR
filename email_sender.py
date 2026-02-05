"""Direct SMTP Email Sender"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict
from lead_repository import LeadRepository


class EmailSender:
    """Direct SMTP email sending (no Flask-Mail)"""

    def __init__(self):
        self.repo = LeadRepository()
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email = os.getenv("GMAIL_EMAIL")
        self.password = os.getenv("GMAIL_PASSWORD")

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
            print(f"Email send error: {e}")
            return False

    def send_pending_emails(self, limit: int = 10) -> Dict:
        """Send all pending emails"""
        print(f"\n{'='*60}")
        print("EMAIL SENDER: Sending Pending Emails")
        print(f"{'='*60}")

        if not self.email or not self.password:
            print("✗ Gmail credentials not configured")
            return {"sent": 0, "failed": 0}

        emails = self.repo.get_pending_emails(limit)
        print(f"Sending {len(emails)} emails...")

        sent = 0
        failed = 0

        for i, email_data in enumerate(emails, 1):
            print(f"\n[{i}/{len(emails)}] {email_data['business_name']}")
            
            success = self.send_email(
                email_data["email"],
                email_data["subject"],
                email_data["body"]
            )

            self.repo.mark_email_sent(email_data["campaign_id"], success)

            if success:
                sent += 1
                print(f"  ✓ Sent to {email_data['email']}")
            else:
                failed += 1
                print(f"  ✗ Failed")

        print(f"\n{'='*60}")
        print(f"Email Sending Complete: {sent} sent, {failed} failed")
        print(f"{'='*60}\n")

        return {"sent": sent, "failed": failed}
