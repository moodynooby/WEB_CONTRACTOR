"""ADK tools for the outreach domain — email generation, saving, sending, refinement."""

import json
from typing import Any

from infra.logging import get_logger

logger = get_logger(__name__)


def generate_email(
    lead_id: str,
    business_name: str,
    bucket: str,
    issues_json: str,
    angle: str = "",
    cta: str = "",
) -> dict[str, Any]:
    """Generate a personalized cold email for a qualified lead using the LLM.

    Args:
        lead_id: MongoDB ObjectId of the lead.
        business_name: Name of the business.
        bucket: Industry bucket name (e.g., ``"Restaurants"``, ``"Developers"``).
        issues_json: JSON string of audit issues (list of dicts with
            ``severity``, ``description``, ``remediation``).
        angle: Optional marketing angle to inject into the email.
        cta: Optional call-to-action text.

    Returns:
        Dict with keys: ``status``, ``subject``, ``body``, ``lead_id``.
    """
    from infra import llm
    from infra.settings import DEFAULT_MODEL, EMAIL_MAX_RETRIES
    from outreach.prompts import (
        format_issues,
        build_email_prompt,
        get_email_system_message,
    )

    try:
        issues = json.loads(issues_json) if isinstance(issues_json, str) else issues_json
    except (json.JSONDecodeError, TypeError):
        issues = []

    issues_text = format_issues(issues)
    prompt = build_email_prompt(
        business_name=business_name,
        bucket=bucket,
        issues_summary=issues_text,
        url="",
        angle=angle,
        cta=cta,
    )
    system_message = get_email_system_message()

    raw = llm.generate(
        model=DEFAULT_MODEL,
        prompt=prompt,
        system=system_message,
        format_json=True,
        max_retries=EMAIL_MAX_RETRIES,
    )
    data = json.loads(raw)
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()

    if not subject or not body:
        return {"status": "error", "error": "LLM returned empty email"}

    return {
        "status": "success",
        "lead_id": lead_id,
        "subject": subject,
        "body": body,
    }


def save_email(
    lead_id: str,
    to_email: str,
    subject: str,
    body: str,
    status: str = "needs_review",
) -> dict[str, Any]:
    """Save a generated email to the database.

    Args:
        lead_id: MongoDB ObjectId of the lead.
        to_email: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        status: Initial status (``needs_review``, ``approved``, ``sent``).

    Returns:
        Dict with keys: ``status``, ``message``.
    """
    from database.email_repo import save_emails_batch

    save_emails_batch([{
        "lead_id": lead_id,
        "to_email": to_email,
        "subject": subject,
        "body": body,
        "status": status,
        "variation": "default",
    }])
    return {"status": "success", "message": f"Email saved for lead {lead_id}"}


def send_email(
    to_email: str,
    subject: str,
    body: str,
    lead_id: str = "",
    campaign_id: str = "",
) -> dict[str, Any]:
    """Send an email via SMTP (Gmail).

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        lead_id: Optional lead ObjectId for tracking.
        campaign_id: Optional campaign ObjectId for tracking.

    Returns:
        Dict with keys: ``status``, ``message``.
    """
    from outreach.sender import EmailSender

    sender = EmailSender()
    success = sender.send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        campaign_id=int(campaign_id) if campaign_id else None,
        lead_id=lead_id or None,
    )
    if success:
        return {"status": "success", "message": f"Email sent to {to_email}"}
    return {"status": "error", "error": "SMTP send returned False"}


def refine_email(
    subject: str,
    body: str,
    instructions: str,
) -> dict[str, Any]:
    """Refine an existing email based on user instructions using the LLM.

    Args:
        subject: Current email subject line.
        body: Current email body text.
        instructions: User instructions for refinement.

    Returns:
        Dict with keys: ``status``, ``subject``, ``body``.
    """
    from infra import llm
    from infra.settings import get_section
    from outreach.prompts import build_refine_prompt

    llm_config = get_section("llm")
    prompt = build_refine_prompt(subject, body, instructions)

    raw = llm.generate(
        model=llm_config.get("default_model", "llama-3.1-8b-instant"),
        prompt=prompt,
        system="You are a professional email editor. Output ONLY valid JSON.",
        format_json=True,
        max_retries=llm_config.get("max_retries", 2),
    )
    data = json.loads(raw)
    return {
        "status": "success",
        "subject": data.get("subject", subject),
        "body": data.get("body", body),
    }
