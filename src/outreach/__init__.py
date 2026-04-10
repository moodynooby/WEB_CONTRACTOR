"""Outreach package for email generation, sending, and contact discovery."""

from .discovery import (
    validate_email,
    find_emails_in_html,
    find_contact_form_email,
    find_phone,
    find_contact_info_from_website,
    scrape_email_from_website,
)
from .sender import EmailSender
from .generator import EmailGenerator

__all__ = [
    "validate_email",
    "find_emails_in_html",
    "find_contact_form_email",
    "find_phone",
    "find_contact_info_from_website",
    "scrape_email_from_website",
    "EmailSender",
    "EmailGenerator",
]
