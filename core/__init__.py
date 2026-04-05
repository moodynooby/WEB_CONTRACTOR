"""Core business logic for Web Contractor.

Single entry point for environment initialization.
All modules should import from here to ensure dotenv is loaded first.
"""

from dotenv import load_dotenv
load_dotenv()  # noqa: E402

from core.settings import load_json_section  # noqa: E402
from core.logging import get_logger, setup_root_logger  # noqa: E402

from core.audit import AuditOrchestrator  # noqa: E402
from core.discovery import PlaywrightScraper  # noqa: E402
from core.email import EmailSender, EmailGenerator  # noqa: E402
from core.llm import (  # noqa: E402
    is_available,
    generate,
    generate_with_retry,
    LLMError,
    ProviderError,
    get_provider_info,
)
from core.app_core import WebContractorApp  # noqa: E402
from core.db_models import (  # noqa: E402
    db,
    Bucket,
    Lead,
    EmailCampaign,
    QueryPerformance,
)
from core.db_repository import (  # noqa: E402
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
