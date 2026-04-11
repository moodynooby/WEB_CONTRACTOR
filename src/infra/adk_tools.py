"""ADK FunctionTools — wrap existing business logic as ADK-callable tools.

Each tool is a plain Python function with type hints and a docstring.
ADK auto-generates the tool schema from the signature, enabling LLMs
to discover and invoke them autonomously.
"""

import json
from typing import Any

from infra.logging import get_logger

logger = get_logger(__name__)



def fetch_website(url: str) -> dict[str, Any]:
    """Fetch a website URL and return parsed HTML content.

    Args:
        url: The website URL to fetch (must include http/https scheme).

    Returns:
        Dict with keys: ``status`` (``success``/``error``), ``html`` (raw HTML
        string), ``soup_text`` (extracted text content), ``status_code`` (int),
        and ``error`` (error message on failure).
    """
    import requests
    from bs4 import BeautifulSoup

    if not url.startswith("http"):
        url = f"https://{url}"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (WebContractor ADK Audit)"},
            timeout=15,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return {
                "status": "success",
                "html": resp.text[:50000],  
                "soup_text": text[:10000],
                "status_code": resp.status_code,
            }
        return {
            "status": "error",
            "error": f"HTTP {resp.status_code}",
            "status_code": resp.status_code,
        }
    except Exception as e:
        logger.warning(f"fetch_website failed for {url}: {e}")
        return {"status": "error", "error": str(e)}


def discover_leads(limit: int = 20) -> dict[str, Any]:
    """Run lead discovery pipeline and return newly discovered leads.

    Wraps :class:`discovery.engine.PlaywrightScraper`.  Returns a summary
    rather than raw lead data — the leads are persisted to MongoDB and
    downstream agents query them from the database.

    Args:
        limit: Maximum number of search queries to execute.

    Returns:
        Dict with keys: ``status``, ``queries_executed``, ``leads_found``,
        ``leads_saved``.
    """
    from discovery.engine import PlaywrightScraper

    scraper = PlaywrightScraper()
    try:
        result = scraper.run(max_queries=limit)
        return {
            "status": "success",
            "queries_executed": result["queries_executed"],
            "leads_found": result["leads_found"],
            "leads_saved": result["leads_saved"],
        }
    except Exception as e:
        logger.error(f"discover_leads failed: {e}")
        return {"status": "error", "error": str(e)}



def get_pending_audits(limit: int = 20) -> dict[str, Any]:
    """Fetch leads that have not yet been audited from the database.

    Args:
        limit: Maximum number of leads to return.

    Returns:
        Dict with keys: ``status``, ``leads`` (list of lead dicts with
        ``id``, ``business_name``, ``website``, ``bucket``, ``email``).
    """
    from database.repository import get_pending_audits as _repo_get

    try:
        leads = _repo_get(limit)
        return {"status": "success", "leads": leads}
    except Exception as e:
        logger.error(f"get_pending_audits failed: {e}")
        return {"status": "error", "error": str(e)}


def save_audit_result(lead_id: str, audit_data: str) -> dict[str, Any]:
    """Persist an audit result to the database.

    Args:
        lead_id: The MongoDB ObjectId of the lead.
        audit_data: JSON string containing the full audit result (score,
            issues, qualified flag, etc.).

    Returns:
        Dict with keys: ``status``, ``message``.
    """
    from database.repository import save_audits_batch

    try:
        data = json.loads(audit_data) if isinstance(audit_data, str) else audit_data
        save_audits_batch([{"lead_id": lead_id, "data": data}])
        return {"status": "success", "message": f"Audit saved for lead {lead_id}"}
    except Exception as e:
        logger.error(f"save_audit_result failed: {e}")
        return {"status": "error", "error": str(e)}


def get_qualified_leads(limit: int = 20) -> dict[str, Any]:
    """Fetch leads that passed the audit qualification threshold.

    Args:
        limit: Maximum number of leads to return.

    Returns:
        Dict with keys: ``status``, ``leads`` (list of lead dicts with
        audit results attached).
    """
    from database.repository import get_qualified_leads as _repo_get

    try:
        leads = _repo_get(limit)
        return {"status": "success", "leads": leads}
    except Exception as e:
        logger.error(f"get_qualified_leads failed: {e}")
        return {"status": "error", "error": str(e)}



def generate_email(
    lead_id: str,
    business_name: str,
    bucket: str,
    issues_json: str,
    angle: str = "",
    cta: str = "",
) -> dict[str, Any]:
    """Generate a personalized cold email for a qualified lead using the LLM.

    The email references specific audit findings (critical/warning issues)
    and uses bucket-specific angles and CTAs when provided.

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

    try:
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
    except Exception as e:
        logger.error(f"generate_email failed: {e}")
        return {"status": "error", "error": str(e)}


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
    from database.repository import save_emails_batch

    try:
        save_emails_batch([{
            "lead_id": lead_id,
            "to_email": to_email,
            "subject": subject,
            "body": body,
            "status": status,
            "variation": "default",
        }])
        return {"status": "success", "message": f"Email saved for lead {lead_id}"}
    except Exception as e:
        logger.error(f"save_email failed: {e}")
        return {"status": "error", "error": str(e)}


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

    try:
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
    except Exception as e:
        logger.error(f"send_email failed: {e}")
        return {"status": "error", "error": str(e)}


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
    import json as _json
    from infra import llm
    from infra.settings import get_section
    from outreach.prompts import build_refine_prompt

    llm_config = get_section("llm")
    prompt = build_refine_prompt(subject, body, instructions)

    try:
        raw = llm.generate(
            model=llm_config.get("default_model", "llama-3.1-8b-instant"),
            prompt=prompt,
            system="You are a professional email editor. Output ONLY valid JSON.",
            format_json=True,
            max_retries=llm_config.get("max_retries", 2),
        )
        data = _json.loads(raw)
        return {
            "status": "success",
            "subject": data.get("subject", subject),
            "body": data.get("body", body),
        }
    except Exception as e:
        logger.error(f"refine_email failed: {e}")
        return {"status": "error", "error": str(e), "subject": subject, "body": body}
