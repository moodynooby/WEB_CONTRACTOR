"""Core business logic for Web Contractor.

Single entry point for environment initialization.
All modules should import from here to ensure dotenv is loaded first.
"""

from dotenv import load_dotenv

load_dotenv()

from infra.settings import load_json_section
from infra.logging import get_logger

from audit.orchestrator import AuditOrchestrator
from discovery.engine import PlaywrightScraper, BucketConfigGenerator
from outreach import EmailSender, EmailGenerator
from infra.llm import (
    is_llm_available,
    generate,
    generate_with_retry,
    LLMError,
    ProviderError,
    generate_bucket_config,
    get_rate_limit_status,
    reset_rate_limits,
)
from app import WebContractorApp
from database.connection import (
    get_database,
    get_client,
    init_db,
    close_db,
    is_connected,
    is_healthy,
    defer_database_write,
    replay_deferred_writes,
    cleanup_old_pending_writes,
    get_email_campaign_stats,
    get_recent_email_campaigns,
    count_email_campaigns,
)
from database.schemas import SearchBucket, Lead, EmailCampaign, QueryPerformance
from database.repository import (
    save_bucket,
    get_all_buckets,
    get_bucket_by_name,
    get_bucket_id_by_name,
    count_leads_pending_audit,
    count_qualified_leads_without_emails,
    count_emails_for_review,
    save_leads_batch,
    get_pending_audits,
    save_audits_batch,
    get_qualified_leads,
    save_emails_batch,
    get_emails_for_review,
    update_email_content,
    delete_email,
    get_lead_by_id,
    mark_email_sent,
    get_or_create_query_performance,
    update_query_performance,
    cleanup_stale_queries,
    count_leads,
)

__all__ = [
    "load_json_section",
    "get_logger",
    "setup_root_logger",
    "WebContractorApp",
    "PlaywrightScraper",
    "BucketConfigGenerator",
    "EmailSender",
    "EmailGenerator",
    "AuditOrchestrator",
    "is_llm_available",
    "generate",
    "generate_with_retry",
    "LLMError",
    "ProviderError",
    "get_provider_info",
    "generate_bucket_config",
    "get_rate_limit_status",
    "reset_rate_limits",
    "get_database",
    "get_client",
    "init_db",
    "close_db",
    "is_connected",
    "is_healthy",
    "defer_database_write",
    "replay_deferred_writes",
    "cleanup_old_pending_writes",
    "get_email_campaign_stats",
    "get_recent_email_campaigns",
    "count_email_campaigns",
    "SearchBucket",
    "Lead",
    "EmailCampaign",
    "QueryPerformance",
    "save_bucket",
    "get_all_buckets",
    "get_bucket_by_name",
    "get_bucket_id_by_name",
    "ensure_indexes",
    "count_leads_pending_audit",
    "count_qualified_leads_without_emails",
    "count_emails_for_review",
    "save_leads_batch",
    "get_pending_audits",
    "save_audits_batch",
    "get_qualified_leads",
    "save_emails_batch",
    "get_emails_for_review",
    "update_email_content",
    "delete_email",
    "get_lead_by_id",
    "mark_email_sent",
    "get_or_create_query_performance",
    "update_query_performance",
    "cleanup_stale_queries",
    "get_all_leads",
    "count_leads",
    "get_query_performance_all",
    "get_email_campaigns",
]
