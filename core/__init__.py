"""Core business logic for Web Contractor."""

from core.discovery import PlaywrightScraper
from core.outreach import Outreach
from core.email import EmailSender
from core.llm import is_available, generate, generate_with_retry, OllamaError
from core.db_peewee import (
    db, init_db, close_db,
    Bucket, Lead, Audit, AuditIssue, EmailCampaign, AppConfig,
    save_bucket, get_all_buckets, get_bucket_id_by_name,
    save_config, get_config,
    save_lead, save_leads_batch, update_lead_contact_info,
    get_pending_audits, save_audit, save_audits_batch,
    get_qualified_leads, stream_qualified_leads,
    save_email, save_emails_batch,
    get_emails_for_review, get_emails_needing_review,
    update_email_status, update_email_content, delete_email, mark_email_sent,
)

__all__ = [
    "PlaywrightScraper",
    "Outreach",
    "EmailSender",
    "is_available",
    "generate",
    "generate_with_retry",
    "OllamaError",
    "db",
    "init_db",
    "close_db",
    "Bucket",
    "Lead",
    "Audit",
    "AuditIssue",
    "EmailCampaign",
    "AppConfig",
    "save_bucket",
    "get_all_buckets",
    "get_bucket_id_by_name",
    "save_config",
    "get_config",
    "save_lead",
    "save_leads_batch",
    "update_lead_contact_info",
    "get_pending_audits",
    "save_audit",
    "save_audits_batch",
    "get_qualified_leads",
    "stream_qualified_leads",
    "save_email",
    "save_emails_batch",
    "get_emails_for_review",
    "get_emails_needing_review",
    "update_email_status",
    "update_email_content",
    "delete_email",
    "mark_email_sent",
]
