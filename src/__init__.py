"""Core business logic for Web Contractor.

Single entry point for environment initialization.
All modules should import from here to ensure dotenv is loaded first.
"""

from dotenv import load_dotenv

load_dotenv()

from infra.settings import load_json_section
from infra.logging import get_logger, setup_root_logger

from audit.orchestrator import AuditOrchestrator
from discovery.engine import PlaywrightScraper, BucketGenerator
from outreach import EmailSender, EmailGenerator
from infra.llm import (
    is_available,
    generate,
    generate_with_retry,
    LLMError,
    ProviderError,
    get_provider_info,
    generate_bucket_config,
)
from gui import App
from database.connection import (
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
from models.schemas import Bucket, Lead, EmailCampaign, QueryPerformance
from database.repository import (
    save_bucket,
    get_all_buckets,
    get_bucket_by_name,
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
    mark_emails_sent_batch,
    get_or_create_query_performance,
    update_query_performance,
    get_query_performance_stats,
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
    "App",
    "PlaywrightScraper",
    "BucketGenerator",
    "EmailSender",
    "EmailGenerator",
    "AuditOrchestrator",
    "is_available",
    "generate",
    "generate_with_retry",
    "LLMError",
    "ProviderError",
    "get_provider_info",
    "generate_bucket_config",
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
    "get_bucket_by_name",
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
    "mark_emails_sent_batch",
    "get_or_create_query_performance",
    "update_query_performance",
    "get_query_performance_stats",
    "cleanup_stale_queries",
    "get_all_leads",
    "count_leads",
    "get_query_performance_all",
    "get_email_campaigns",
]
