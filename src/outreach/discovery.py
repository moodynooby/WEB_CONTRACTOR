"""Contact discovery functions for extracting email and phone info from websites."""

import re
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

try:
    from email_scraper import scrape_emails
except ImportError:
    scrape_emails: Callable | None = None

try:
    from mailscout import Scout
except ImportError:
    Scout: type | None = None

import email_validator
import requests

from infra.settings import (
    DEFAULT_USER_AGENT,
    EMAIL_SCRAPE_TIMEOUT,
    EMAIL_COMMON_PREFIXES,
)


def validate_email(email: str) -> Optional[str]:
    """Validate and normalize email."""
    if not email or len(email) > 254 or "@" not in email:
        return None
    try:
        email_obj = email_validator.validate_email(email, check_deliverability=False)
        return email_obj.normalized
    except email_validator.EmailNotValidError:
        return None


def find_emails_in_html(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Find all valid emails in HTML."""
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
    """Attempt to generate business email using mailscout as fallback."""
    if Scout is None:
        return None

    try:
        parsed = urlparse(base_url)
        domain = parsed.netloc or parsed.path
        if not domain:
            return None

        domain = domain.replace("www.", "")

        for prefix in EMAIL_COMMON_PREFIXES:
            test_email = f"{prefix}@{domain}"
            if validate_email(test_email):
                return test_email

        scout = Scout(check_variants=False, check_prefixes=True)
        emails = scout.find_emails(domain, EMAIL_COMMON_PREFIXES)
        if emails and hasattr(emails, "__iter__"):
            for em in emails:
                normalized = validate_email(em)
                if normalized:
                    return normalized

    except Exception:
        pass

    return None


def discover_contact_info(html_content: str, base_url: str) -> Dict[str, Optional[str]]:
    """Discover contact information from website HTML."""
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
    """Attempt to scrape email from website URL."""
    try:
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        response = requests.get(
            website_url, headers=headers, timeout=EMAIL_SCRAPE_TIMEOUT
        )
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
