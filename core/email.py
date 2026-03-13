"""SMTP Email Sender - Simplified single-threaded design

Uses direct SMTP with context manager for efficient connection handling.

Also contains EmailGenerator class for generating personalized cold emails
for qualified leads based on their audit results.

Also contains contact discovery functions for extracting email and phone 
information from websites.
"""

import json
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import email_validator


from core import llm
from core.db_repository import (
    get_qualified_leads,
    mark_email_sent,
    save_emails_batch,
)
from core.utils import load_json_config


def validate_email(email: str) -> Optional[str]:
    """Validate and normalize email using email-validator library."""
    if not email or len(email) > 254 or "@" not in email:
        return None
    try:
        email_obj = email_validator.validate_email(email, check_deliverability=True)
        return email_obj.normalized
    except email_validator.EmailNotValidError:
        return None


def find_emails_in_html(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Find all valid emails in HTML from mailto links and text content."""
    emails: List[str] = []
    seen: Set[str] = set()

    for elem in soup.find_all(True):
        href = elem.get("href", "")
        if href and isinstance(href, str) and "mailto:" in href.lower():
            for e in href.lower().replace("mailto:", "").split(","):
                normalized = validate_email(e.strip())
                if normalized and normalized not in seen:
                    emails.append(normalized)
                    seen.add(normalized)

        onclick = elem.get("onclick", "")
        if onclick and "mailto:" in str(onclick).lower():
            for match in re.findall(r"mailto:([^\s\'\",;]+)", str(onclick), re.I):
                normalized = validate_email(match.lower().strip())
                if normalized and normalized not in seen:
                    emails.append(normalized)
                    seen.add(normalized)

    text = soup.get_text(separator=" ", strip=True)
    for pattern in [
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        r"[\(\<\[]([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})[\)\>\]]",
    ]:
        for match in re.findall(pattern, text):
            normalized = validate_email(match.lower().strip())
            if normalized and normalized not in seen:
                emails.append(normalized)
                seen.add(normalized)

    return emails


def find_contact_form_email(soup: BeautifulSoup, base_url: str) -> Tuple[Optional[str], Optional[str]]:
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


def discover_contact_info(html_content: str, base_url: str) -> Dict[str, Optional[str]]:
    """Discover contact information from website HTML.
    
    """
    soup = BeautifulSoup(html_content, "html.parser")

    emails = find_emails_in_html(soup, base_url)
    email = emails[0] if emails else None

    form_email, form_url = find_contact_form_email(soup, base_url)
    if not email and form_email:
        email = form_email

    phone = find_phone(soup)

    return {
        "email": email,
        "phone": phone,
    }


class EmailSender:
    """SMTP Email Sender - simplified without connection pooling"""

    def __init__(
        self,
        logger: Callable | None = None,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
        email: str | None = None,
        password: str | None = None,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email = email or __import__("os").getenv("GMAIL_EMAIL")
        self.password = password or __import__("os").getenv("GMAIL_PASSWORD")
        self.logger = logger
        self.email_signature = "\n\nBest regards,\nManas Doshi,\nFuture Forwards - https://man27.netlify.app/services"

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def send_email(
        self, to_email: str, subject: str, body: str, campaign_id: int | None = None
    ) -> bool:
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

            return True  # type: ignore[no-any-return]
        except Exception as e:
            self.log(f"Email send error: {e}", "error")
            if campaign_id:
                mark_email_sent(campaign_id, False, str(e))
            return False


class EmailGenerator:
    """
    Generates personalized cold emails for qualified leads.

    This is separate from the audit process - it takes already-audited
    leads that have been marked as qualified and generates emails for them.
    """

    def __init__(
        self,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        self.logger: Callable[[str, str], None] = logger or (
            lambda msg, style: print(f"[{style}] {msg}")
        )
        self.audit_settings = load_json_config("audit_settings.json")
        self.email_config = self.audit_settings.get("email_generation", {})
        self.app_settings = load_json_config("app_settings.json")

    def log(self, message: str, style: str = "") -> None:
        """Log message with style."""
        self.logger(message, style)

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
                issues=issues_text,
            )

            if angle:
                prompt += f"\n\nAngle: {angle}"
            if cta:
                prompt += f"\nCTA: {cta}"

            system_message = self.email_config.get("system_message", "")

            email_start = time.time()
            try:
                raw = llm.generate(
                    model=self.email_config.get("model", "llama-3.1-8b-instant"),
                    prompt=prompt,
                    system=system_message,
                    format_json=True,
                    timeout=self.email_config.get("timeout", 30),
                )
                data = json.loads(raw)

                subject = data.get("subject", "")
                body = data.get("body", "")

                if not subject or not body:
                    self.log("  ⚠ LLM returned empty email", "warning")
                    continue

                email_data = {
                    "lead_id": lead["id"],
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
        llm_settings = self.app_settings.get("llm_settings", {})

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
