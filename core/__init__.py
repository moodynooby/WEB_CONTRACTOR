"""Core business logic for Web Contractor."""

from core.discovery import PlaywrightScraper
from core.outreach import Outreach
from core.email import EmailSender
from core.llm import is_available, generate, generate_with_retry, OllamaError
from core.app_core import WebContractorApp, Config
from core.db_models import (
    db, Bucket, Lead, Audit, AuditIssue, EmailCampaign, AppConfig, QueryPerformance,
)
from core.db_repository import (
    init_db, close_db,
    save_bucket, get_all_buckets, get_bucket_id_by_name,
    save_config, get_config,
    save_lead, save_leads_batch, update_lead_contact_info,
    get_pending_audits, save_audits_batch,
    get_qualified_leads,
    save_emails_batch,
    get_emails_for_review,
    update_email_content, delete_email, mark_email_sent,
)
from core.utils import load_json_config

__all__ = [
    "load_json_config",
    "WebContractorApp",
    "Config",
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
    "QueryPerformance",
    "save_bucket",
    "get_all_buckets",
    "get_bucket_id_by_name",
    "save_config",
    "get_config",
    "save_lead",
    "save_leads_batch",
    "update_lead_contact_info",
    "get_pending_audits",
    "save_audits_batch",
    "get_qualified_leads",
    "save_emails_batch",
    "get_emails_for_review",
    "update_email_content",
    "delete_email",
    "mark_email_sent",
]
