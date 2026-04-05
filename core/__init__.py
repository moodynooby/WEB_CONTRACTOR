"""Core business logic for Web Contractor.

Single entry point for environment initialization.
All modules should import from here to ensure dotenv is loaded first.
"""

from dotenv import load_dotenv

load_dotenv()

from core.settings import load_json_section
from core.logging import get_logger, setup_root_logger

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
from core.app_core import WebContractorApp
from core.db import (
    get_database,
    get_client,
    init_db,
    close_db,
    is_connected,
    is_healthy,
    queue_pending_write,
    flush_pending_writes,
    cleanup_old_pending_writes,
    get_circuit_breaker_state,
    get_email_campaign_stats,
    get_recent_email_campaigns,
    count_email_campaigns,
)
from core.models import Bucket, Lead, EmailCampaign, QueryPerformance
from core.repository import (
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
    get_all_leads,
    count_leads,
    get_query_performance_all,
    get_email_campaigns,
)

__all__ = [
    "load_json_section",
    "get_logger",
    "setup_root_logger",
    "WebContractorApp",
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
    "get_database",
    "get_client",
    "init_db",
    "close_db",
    "is_connected",
    "is_healthy",
    "queue_pending_write",
    "flush_pending_writes",
    "cleanup_old_pending_writes",
    "get_circuit_breaker_state",
    "get_email_campaign_stats",
    "get_recent_email_campaigns",
    "count_email_campaigns",
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
    "get_all_leads",
    "count_leads",
    "get_query_performance_all",
    "get_email_campaigns",
]
