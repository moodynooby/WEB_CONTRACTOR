"""SMTP Email Sender - Simplified single-threaded design.

Uses direct SMTP with context manager for efficient connection handling.

Also contains EmailGenerator class for generating personalized cold emails
for qualified leads based on their audit results.

Also contains contact discovery functions for extracting email and phone
information from websites.
"""

import json
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import email_validator

try:
    from email_scraper import scrape_emails
except ImportError:
    scrape_emails = None

try:
    from mailscout import Scout
except ImportError:
    Scout = None


from core import llm
from core.settings import (
    DEFAULT_USER_AGENT,
    EMAIL_SIGNATURE,
    SMTP_SERVER,
    SMTP_PORT,
    GMAIL_EMAIL,
    GMAIL_PASSWORD,
    DEFAULT_MODEL,
    EMAIL_MAX_RETRIES,
    load_json_section,
)
from core.logging import get_logger
from core.repository import (
    get_qualified_leads,
    mark_email_sent,
    save_emails_batch,
    update_lead_status,
)


def validate_email(email: str) -> Optional[str]:
    """Validate and normalize email using email-validator library.

    Note: Deliverability check disabled for performance since we only
    need to verify format, not actual email existence.
    """
    if not email or len(email) > 254 or "@" not in email:
        return None
    try:
        email_obj = email_validator.validate_email(email, check_deliverability=False)
        return email_obj.normalized
    except email_validator.EmailNotValidError:
        return None


def find_emails_in_html(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Find all valid emails in HTML using email-scraper library.

    Uses email-scraper for extraction (handles obfuscated emails),
    then validates with email-validator.
    """
    import re

    emails: List[str] = []
    seen: set = set()

    if scrape_emails is not None:
        html_str = str(soup)
        scraped = scrape_emails(html_str)
        for email in scraped:
            normalized = validate_email(email)
            if normalized and normalized not in seen:
                emails.append(normalized)
                seen.add(normalized)
    else:
        text = soup.get_text(separator=" ", strip=True)
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        for match in re.findall(pattern, text):
            normalized = validate_email(match.lower().strip())
            if normalized and normalized not in seen:
                emails.append(normalized)
                seen.add(normalized)

    return emails


def find_contact_form_email(
    soup: BeautifulSoup, base_url: str
) -> Tuple[Optional[str], Optional[str]]:
    """Extract email from contact form action URLs."""
    for form in soup.find_all("form"):
        action = form.get("action", "")
        if not action or not isinstance(action, str):
            continue

        form_url = (
            urljoin(base_url, action) if not action.startswith("http") else action
        )

        if "mailto:" in action.lower():
            email = action.lower().replace("mailto:", "").strip()
            normalized = validate_email(email)
            if normalized:
                return (normalized, form_url)

        parsed = urlparse(form_url)
        for param in ["email", "to", "recipient", "_replyto"]:
            if param in parsed.query:
                for value in parse_qs(parsed.query).get(param, []):
                    normalized = validate_email(value)
                    if normalized:
                        return (normalized, form_url)

    return (None, None)


def find_phone(soup: BeautifulSoup) -> Optional[str]:
    """Extract phone number from tel: links."""
    for link in soup.find_all("a", href=True):
        href = str(link.get("href", ""))
        if href.startswith("tel:"):
            return href.replace("tel:", "")
    return None


def _try_mailscout_fallback(base_url: str) -> Optional[str]:
    """Attempt to generate business email using mailscout as fallback.

    Uses common patterns like info@, contact@, hello@ + domain.
    Only used when no email found on website.
    """
    if Scout is None:
        return None

    try:
        parsed = urlparse(base_url)
        domain = parsed.netloc or parsed.path
        if not domain:
            return None

        domain = domain.replace("www.", "")

        common_prefixes = ["info", "contact", "hello", "support", "admin"]
        for prefix in common_prefixes:
            test_email = f"{prefix}@{domain}"
            if validate_email(test_email):
                return test_email

        scout = Scout(check_variants=False, check_prefixes=True)
        emails = scout.find_emails(domain, common_prefixes)
        if emails and hasattr(emails, "__iter__"):
            for em in emails:
                normalized = validate_email(em)
                if normalized:
                    return normalized

    except Exception:
        pass

    return None


def discover_contact_info(html_content: str, base_url: str) -> Dict[str, Optional[str]]:
    """Discover contact information from website HTML.

    Uses email-scraper for extraction, with mailscout as fallback
    for generating business emails when none found on website.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    emails = find_emails_in_html(soup, base_url)
    email = emails[0] if emails else None

    form_email, form_url = find_contact_form_email(soup, base_url)
    if not email and form_email:
        email = form_email

    if not email:
        email = _try_mailscout_fallback(base_url)

    phone = find_phone(soup)

    return {
        "email": email,
        "phone": phone,
    }


def scrape_email_from_website(website_url: str) -> Optional[str]:
    """Attempt to scrape email from website URL.

    Fetches the website HTML and extracts email addresses.
    Uses email-scraper library with validation fallback.
    """

    try:
        import requests

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        response = requests.get(website_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        emails = find_emails_in_html(soup, website_url)

        if emails:
            return emails[0]

        form_email, _ = find_contact_form_email(soup, website_url)
        if form_email:
            return form_email

        email = _try_mailscout_fallback(website_url)
        return email

    except Exception:
        return None


class EmailSender:
    """SMTP Email Sender."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
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
        self, to_email: str, subject: str, body: str, campaign_id: int | None = None
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
                mark_email_sent(campaign_id, True)

            return True  # type: ignore[no-any-return]
        except Exception as e:
            self.log(f"Email send error: {e}", "error")
            if campaign_id:
                mark_email_sent(campaign_id, False, str(e))
            return False


class EmailGenerator:
    """Generates personalized cold emails for qualified leads."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.email_config = load_json_section("email_generation")
        self.llm_config = load_json_section("llm")

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

    def generate(
        self, limit: int = 20, progress_callback: Callable | None = None
    ) -> dict:
        """Generate emails for qualified leads.

        Args:
            limit: Maximum number of leads to generate emails for
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with count of generated emails
        """
        self.log("\n=== EMAIL GENERATION ===", "info")

        leads = get_qualified_leads(limit)
        self.log(f"Found {len(leads)} qualified leads", "info")

        if not leads:
            return {"generated": 0}

        generated = 0
        email_batch = []

        for i, lead in enumerate(leads, 1):
            lead_email = (lead.get("email") or "").strip()
            if not lead_email:
                self.log(
                    f"  [{i}/{len(leads)}] {lead['business_name']} - "
                    "No email, attempting to scrape...",
                    "info",
                )
                website = lead.get("website", "")
                if website:
                    lead_email = scrape_email_from_website(website)
                    if lead_email:
                        self.log(
                            f"  [{i}/{len(leads)}] {lead['business_name']} - "
                            f"Found email: {lead_email}",
                            "success",
                        )
                    else:
                        self.log(
                            f"  [{i}/{len(leads)}] {lead['business_name']} - "
                            "No email found, skipping",
                            "warning",
                        )
                        update_lead_status(lead["id"], "unqualified")
                        continue
                else:
                    self.log(
                        f"  [{i}/{len(leads)}] {lead['business_name']} - "
                        "No website, skipping",
                        "warning",
                    )
                    update_lead_status(lead["id"], "unqualified")
                    continue

            self.log(f"  [{i}/{len(leads)}] {lead['business_name']}", "info")

            issues = lead.get("issues_json", [])
            if not isinstance(issues, list):
                issues = json.loads(issues)

            critical_issues = [i for i in issues if i.get("severity") == "critical"]
            warning_issues = [i for i in issues if i.get("severity") == "warning"]
            top_issues = (critical_issues + warning_issues)[:3]
            issues_text = "\n".join([f"- {i['description']}" for i in top_issues])

            bucket_templates = self.email_config.get("bucket_templates", {})
            bucket_template = bucket_templates.get(lead.get("bucket", "default"), {})
            angle = bucket_template.get("angle", "")
            cta = bucket_template.get("cta", "")

            prompt = self.email_config.get("prompt_template", "").format(
                business_name=lead["business_name"],
                bucket=lead.get("bucket", "default"),
                url=lead["website"],
                issue_summary=issues_text,
            )

            if angle:
                prompt += f"\n\nAngle: {angle}"
            if cta:
                prompt += f"\nCTA: {cta}"

            system_message = self.email_config.get("system_message", "")

            email_start = time.time()
            try:
                raw = llm.generate_with_retry(
                    model=DEFAULT_MODEL,
                    prompt=prompt,
                    system=system_message,
                    format_json=True,
                    max_retries=EMAIL_MAX_RETRIES,
                    timeout=self.email_config.get("timeout", 30),
                )
                data = json.loads(raw)

                subject = (data.get("subject") or "").strip()
                body = (data.get("body") or "").strip()

                if not subject or not body:
                    self.log("  ⚠ LLM returned empty email, retrying...", "warning")
                    raise ValueError("Empty subject or body")

                if len(body) < 20:
                    self.log("  ⚠ Email too short, retrying...", "warning")
                    raise ValueError("Email too short")

                email_data = {
                    "lead_id": lead["id"],
                    "to_email": lead_email,
                    "subject": subject,
                    "body": body,
                    "status": "needs_review",
                    "variation": "default",
                    "duration": time.time() - email_start,
                }
                email_batch.append(email_data)
                generated += 1

            except Exception as e:
                self.log(f"  ⚠ Email generation failed: {e}", "error")

            if progress_callback:
                progress_callback(
                    i, len(leads), f"Generating for {lead['business_name']}"
                )

        if email_batch:
            save_emails_batch(email_batch)
            self.log(f"  Saved {len(email_batch)} emails", "success")

        self.log(f"Email Generation Complete: {generated} emails generated", "success")

        return {"generated": generated}

    def refine(
        self,
        subject: str,
        body: str,
        instructions: str,
    ) -> dict[str, str]:
        """Refine an existing email based on user instructions using LLM.

        Args:
            subject: Current subject line
            body: Current email body
            instructions: Instructions for how to refine the email

        Returns:
            Dict with refined subject and body
        """
        llm_settings = self.llm_config

        if not self.email_config.get("enabled", True):
            self.log("Email refinement disabled", "warning")
            return {"subject": subject, "body": body}

        prompt = f"""Refine this cold email based on instructions.

Instructions: {instructions}

Current Subject: {subject}
Current Body:
{body}

Return ONLY JSON: {{"subject": "refined subject line", "body": "refined email body"}}"""

        try:
            raw = llm.generate_with_retry(
                model=llm_settings.get("default_model", "llama-3.1-8b-instant"),
                prompt=prompt,
                system="You are a professional email editor. Output ONLY valid JSON.",
                format_json=True,
                max_retries=llm_settings.get("max_retries", 2),
                timeout=llm_settings.get("timeout_seconds", 30),
            )
            data = json.loads(raw)
            return {
                "subject": data.get("subject", subject),
                "body": data.get("body", body),
            }
        except llm.ProviderError as e:
            self.log(f"Email refinement failed: {e}", "error")
            return {"subject": subject, "body": body}
