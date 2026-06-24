"""Email service - decoupled email review operations.

Provides all email CRUD + LLM operations as framework-agnostic methods.
"""

from database.email_repo import (
    get_emails_for_review,
    update_email_content,
    delete_email as repo_delete_email,
)
from database.lead_repo import get_lead_by_id
from outreach.generator import EmailGenerator
from outreach.sender import EmailSender
from infra.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """Email review and management operations, decoupled from any UI framework."""

    def __init__(self, email_generator: EmailGenerator | None = None, email_sender: EmailSender | None = None):
        self._generator = email_generator or EmailGenerator()
        self._sender = email_sender or EmailSender()

    def get_emails(self, limit: int = 50) -> list[dict]:
        """Fetch emails pending review."""
        return get_emails_for_review(limit=limit)

    def approve(self, campaign_id: str, subject: str, body: str) -> None:
        self._validate_not_empty(subject, body)
        update_email_content(campaign_id, subject, body)
        logger.info(f"Approved email {campaign_id}")

    def delete(self, campaign_id: str) -> None:
        repo_delete_email(campaign_id)
        logger.info(f"Deleted email {campaign_id}")

    def refine(self, campaign_id: str, instructions: str, current_subject: str, current_body: str) -> dict:
        self._validate_not_empty(current_subject, current_body)
        if not instructions.strip():
            raise ValueError("Instructions cannot be empty")
        result = self._generator.refine(current_subject, current_body, instructions)
        logger.info(f"Refined email {campaign_id}")
        return result

    def regenerate(self, campaign_id: str, lead_id: str) -> dict:
        lead = get_lead_by_id(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")
        result = self._generator.generate_for_lead(lead)
        logger.info(f"Regenerated email {campaign_id}")
        return result

    def send(self, campaign_id: str, to_email: str, subject: str, body: str, lead_id: str | None = None) -> bool:
        self._validate_not_empty(subject, body)
        if not to_email:
            raise ValueError("Recipient email is required")
        success = self._sender.send_email(
            to_email=to_email,
            subject=subject,
            body=body,
            campaign_id=int(campaign_id) if campaign_id.isdigit() else None,
            lead_id=lead_id,
        )
        if success:
            logger.info(f"Email sent to {to_email}")
        else:
            logger.error(f"Failed to send email to {to_email}")
        return success

    def approve_all(self, emails: list[dict]) -> int:
        """Approve all given emails with their current content.

        Args:
            emails: List of email dicts with 'id', 'subject', 'body' keys.

        Returns:
            Number of successfully approved emails.
        """
        approved = 0
        for email in emails:
            try:
                subject = (email.get("subject") or "").strip()
                body = (email.get("body") or "").strip()
                if subject and body:
                    update_email_content(email["id"], subject, body)
                    approved += 1
            except Exception as e:
                logger.error(f"Failed to approve {email.get('id')}: {e}")
        logger.info(f"Approved {approved} emails")
        return approved

    @staticmethod
    def _validate_not_empty(subject: str, body: str) -> None:
        if not subject.strip():
            raise ValueError("Subject cannot be empty")
        if not body.strip():
            raise ValueError("Body cannot be empty")
