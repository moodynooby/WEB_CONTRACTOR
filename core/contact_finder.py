"""Contact Discovery Module - Extract contact info from website HTML

Priority order:
1. mailto: links (most reliable)
2. Contact form action emails
3. Email addresses in text content
"""

import re
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from email_validator import EmailNotValidError, validate_email


class ContactFinder:
    """Extract contact information from website HTML"""

    def __init__(self, logger: Callable | None = None) -> None:
        self.logger = logger

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print."""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def _validate_email(self, email: str) -> str | None:
        """Validate and normalize email using email-validator library."""
        if not email or len(email) > 254 or "@" not in email:
            return None

        try:
            return validate_email(email, check_deliverability=True).normalized
        except EmailNotValidError:
            return None

    def _find_emails_in_html(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Find all valid emails in HTML from mailto links and text content."""
        emails: list[str] = []
        seen: set[str] = set()

        for elem in soup.find_all(True):
            href = elem.get("href", "")
            if href and isinstance(href, str) and "mailto:" in href.lower():
                for e in href.lower().replace("mailto:", "").split(","):
                    normalized = self._validate_email(e.strip())
                    if normalized and normalized not in seen:
                        emails.append(normalized)
                        seen.add(normalized)

            onclick = elem.get("onclick", "")
            if onclick and "mailto:" in str(onclick).lower():
                for match in re.findall(r"mailto:([^\s\'\",;]+)", str(onclick), re.I):
                    normalized = self._validate_email(match.lower().strip())
                    if normalized and normalized not in seen:
                        emails.append(normalized)
                        seen.add(normalized)

        text = soup.get_text(separator=" ", strip=True)
        for pattern in [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            r"[\(\<\[]([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})[\)\>\]]",
        ]:
            for match in re.findall(pattern, text):
                normalized = self._validate_email(match.lower().strip())
                if normalized and normalized not in seen:
                    emails.append(normalized)
                    seen.add(normalized)

        return emails

    def _find_contact_form_email(
        self, soup: BeautifulSoup, base_url: str
    ) -> tuple[str | None, str | None]:
        """Extract email from contact form action URLs."""
        for form in soup.find_all("form"):
            action = form.get("action", "")
            if not action or not isinstance(action, str):
                continue

            form_url = urljoin(base_url, action) if not action.startswith("http") else action

            if "mailto:" in action.lower():
                email = action.lower().replace("mailto:", "").strip()
                normalized = self._validate_email(email)
                if normalized:
                    return (normalized, form_url)

            parsed = urlparse(form_url)
            for param in ["email", "to", "recipient", "_replyto"]:
                if param in parsed.query:
                    for value in parse_qs(parsed.query).get(param, []):
                        normalized = self._validate_email(value)
                        if normalized:
                            return (normalized, form_url)

        return (None, None)

    def _find_social_links(self, soup: BeautifulSoup) -> dict[str, str]:
        """Extract social media links from HTML."""
        social: dict[str, str] = {}
        domains = {
            "linkedin": "linkedin.com",
            "facebook": "facebook.com",
            "instagram": "instagram.com",
            "twitter": ["twitter.com", "x.com"],
        }

        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            href_lower = href.lower()
            for platform, domain in domains.items():
                if isinstance(domain, list):
                    if any(d in href_lower for d in domain) and platform not in social:
                        social[platform] = href
                elif isinstance(domain, str) and domain in href_lower and platform not in social:
                    social[platform] = href

        return social

    def _find_contact_page_url(self, soup: BeautifulSoup, base_url: str) -> str | None:
        """Find contact page URL from navigation links."""
        keywords = ["contact", "get-in-touch", "support"]
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            if any(k in href.lower() for k in keywords):
                return urljoin(base_url, href) if not href.startswith("http") else href
        return None

    def _find_phone(self, soup: BeautifulSoup) -> str | None:
        """Extract phone number from tel: links."""
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            if href.startswith("tel:"):
                return href.replace("tel:", "")
        return None

    def discover_contact_info(self, html_content: str, base_url: str) -> dict:
        """Discover contact information from website HTML.

        Priority order:
        1. mailto: links (most reliable)
        2. Contact form action emails
        3. Email addresses in text content

        Returns:
            dict with keys: email, social_links, contact_form_url, phone
        """
        soup = BeautifulSoup(html_content, "html.parser")

        emails = self._find_emails_in_html(soup, base_url)
        email = emails[0] if emails else None

        form_email, form_url = self._find_contact_form_email(soup, base_url)
        if not email and form_email:
            email = form_email

        return {
            "email": email,
            "social_links": self._find_social_links(soup),
            "contact_form_url": form_url or self._find_contact_page_url(soup, base_url),
            "phone": self._find_phone(soup),
        }
