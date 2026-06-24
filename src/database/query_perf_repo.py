"""Query performance repository — tracking and staleness for search queries."""

from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument

from database._helpers import get_db, to_object_id, sanitize_documents
from infra.logging import get_logger

logger = get_logger(__name__)


def get_or_create_query_performance(
    bucket_id: str, query_pattern: str, city: str
) -> dict | None:
    """Get or create query performance tracking record using upsert."""
    db = get_db()

    try:
        filter_doc = {
            "bucket_id": bucket_id,
            "query_pattern": query_pattern,
            "city": city,
        }

        update = {
            "$setOnInsert": {
                "bucket_id": bucket_id,
                "query_pattern": query_pattern,
                "city": city,
                "is_active": True,
                "total_executions": 0,
                "total_leads_found": 0,
                "total_leads_saved": 0,
                "total_qualified": 0,
                "consecutive_failures": 0,
                "created_at": datetime.now(timezone.utc),
            }
        }

        result = db.query_performance.find_one_and_update(
            filter_doc,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        if result:
            from database._helpers import sanitize_document
            return sanitize_document(result)
        return None
    except Exception as e:
        logger.error(f"Error getting/creating query performance: {e}")
        return None


def update_query_performance(
    qp_id: str,
    leads_found: int,
    leads_saved: int,
    qualified_count: int = 0,
    success: bool = True,
) -> None:
    """Update query performance metrics."""
    db = get_db()

    try:
        inc_data: dict[str, Any] = {
            "total_executions": 1,
            "total_leads_found": leads_found,
            "total_leads_saved": leads_saved,
            "total_qualified": qualified_count,
        }
        set_data: dict[str, Any] = {"last_executed_at": datetime.now(timezone.utc)}

        if success and leads_found > 0:
            set_data["consecutive_failures"] = 0
        else:
            inc_data["consecutive_failures"] = 1

        update: dict[str, Any] = {
            "$inc": inc_data,
            "$set": set_data,
        }

        oid = to_object_id(qp_id)
        db.query_performance.update_one({"_id": oid}, update)
    except ValueError as e:
        logger.error(f"Invalid query performance ID: {e}")
    except Exception as e:
        logger.error(f"Error updating query performance: {e}")


def mark_query_as_stale(qp_id: str) -> None:
    """Mark a query as stale."""
    db = get_db()

    try:
        oid = to_object_id(qp_id)
        db.query_performance.update_one({"_id": oid}, {"$set": {"is_active": False}})
    except ValueError as e:
        logger.error(f"Invalid query performance ID: {e}")
    except Exception as e:
        logger.error(f"Error marking query as stale: {e}")


def get_stale_queries(
    max_failures: int = 3, bucket_id: str | None = None
) -> list[dict]:
    """Get queries that have exceeded failure threshold."""
    db = get_db()

    try:
        query: dict = {
            "is_active": True,
            "consecutive_failures": {"$gte": max_failures},
        }
        if bucket_id:
            query["bucket_id"] = bucket_id

        results = list(db.query_performance.find(query))
        return sanitize_documents(results)
    except Exception as e:
        logger.error(f"Error fetching stale queries: {e}")
        return []


def cleanup_stale_queries(days_threshold: int = 30) -> int:
    """Clean up very old stale queries."""
    db = get_db()

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        result = db.query_performance.delete_many(
            {
                "is_active": False,
                "last_executed_at": {"$lt": cutoff_date},
            }
        )
        if result.deleted_count > 0:
            logger.info(f"Cleaned up {result.deleted_count} stale queries")
        return result.deleted_count
    except Exception as e:
        logger.error(f"Error cleaning up stale queries: {e}")
        return 0
