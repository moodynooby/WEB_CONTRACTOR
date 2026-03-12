"""Core business logic for Web Contractor."""

from core.audit import AuditOrchestrator
from core.discovery import PlaywrightScraper
from core.email import EmailSender, EmailGenerator
from core.llm import (
    is_available,
    generate,
    generate_with_retry,
    LLMError,
    ProviderError,
    get_provider_info,
)
from core.app_core import WebContractorApp, Config
from core.db_models import (
    db,
    Bucket,
    Lead,
    EmailCampaign,
    QueryPerformance,
)
from core.db_repository import (
    init_db,
    close_db,
    save_bucket,
    get_all_buckets,
    get_bucket_id_by_name,
    save_lead,
    save_leads_batch,
    update_lead_contact_info,
    get_pending_audits,
    save_audits_batch,
    get_qualified_leads,
    save_emails_batch,
    get_emails_for_review,
    update_email_content,
    delete_email,
    mark_email_sent,
    cleanup_stale_queries,
)
from core.utils import load_json_config

__all__ = [
    "load_json_config",
    "WebContractorApp",
    "Config",
    "PlaywrightScraper",
    "EmailSender",
    "EmailGenerator",
    "AuditOrchestrator",
    "is_available",
    "generate",
    "generate_with_retry",
    "LLMError",
    "ProviderError",
    "get_provider_info",
    "db",
    "init_db",
    "close_db",
    "Bucket",
    "Lead",
    "EmailCampaign",
    "QueryPerformance",
    "save_bucket",
    "get_all_buckets",
    "get_bucket_id_by_name",
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
    "cleanup_stale_queries",
]
