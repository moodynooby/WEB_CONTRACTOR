"""Stats service - decoupled dashboard statistics.

Provides database statistics as framework-agnostic methods.
"""

from database.connection import is_connected, get_connection_status
from database.repository import (
    count_buckets,
    count_leads_pending_audit,
    count_qualified_leads_without_emails,
    count_emails_for_review,
)
from infra.logging import get_logger

logger = get_logger(__name__)


class StatsService:
    """Dashboard statistics, decoupled from any UI framework."""

    @staticmethod
    def get_db_status() -> dict:
        """Get database connection status."""
        status = get_connection_status()
        return {
            "connected": status.get("connected", False),
            "healthy": status.get("healthy", False),
            "database": status.get("database", ""),
        }

    @staticmethod
    def is_connected() -> bool:
        return is_connected()

    @staticmethod
    def get_stats() -> dict:
        """Get all dashboard statistics as a dict."""
        if not is_connected():
            return {
                "Buckets": 0,
                "Pending Audits": 0,
                "Qualified Leads": 0,
                "Emails for Review": 0,
            }
        try:
            return {
                "Buckets": count_buckets(),
                "Pending Audits": count_leads_pending_audit(),
                "Qualified Leads": count_qualified_leads_without_emails(),
                "Emails for Review": count_emails_for_review(),
            }
        except Exception as e:
            logger.error(f"Failed to refresh stats: {e}")
            return {
                "Buckets": 0,
                "Pending Audits": 0,
                "Qualified Leads": 0,
                "Emails for Review": 0,
            }
