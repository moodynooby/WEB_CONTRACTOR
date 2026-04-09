"""Repository Layer for MongoDB operations - Sync version for Streamlit.

Uses PyMongo directly (no async wrappers needed!).

Features:
- Aggregation pipelines with $lookup for efficient joins
- Bulk write operations for batch updates
- Cursor-based pagination for large collections
- Better error handling with explicit logging
- Projection to limit returned fields
- Centralized document sanitization helpers
- Index management for query performance
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo import UpdateOne, ReturnDocument, ASCENDING, DESCENDING

from database.connection import get_database, queue_pending_write, DatabaseUnavailableError
from infra.logging import get_logger

logger = get_logger(__name__)


def _get_db():
    """Get the database instance from db module.

    Raises DatabaseUnavailableError if the database is not available.
    Callers should catch this exception to show proper error messages.
    """
    db = get_database()
    if db is None:
        raise DatabaseUnavailableError(
            "Database is not connected. Check MONGODB_URI configuration."
        )
    return db


def _to_object_id(id_str: str) -> ObjectId:
    """Convert string ID to ObjectId safely."""
    if isinstance(id_str, ObjectId):
        return id_str
    try:
        return ObjectId(id_str)
    except Exception:
        raise ValueError(f"Invalid ObjectId: {id_str}")


def _sanitize_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB document to API-friendly format.

    - Converts _id ObjectId to string 'id' field
    - Handles nested ObjectId in common fields
    """
    result = doc.copy()
    result["id"] = str(result.pop("_id"))
    return result


def _sanitize_documents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize a list of documents."""
    return [_sanitize_document(doc) for doc in docs]



def save_bucket(data: dict[str, Any]) -> dict[str, Any]:
    """Save or update bucket. Returns the saved bucket data with id.

    Uses upsert to reduce the check-then-insert pattern to a single operation.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        bucket_data = {k: v for k, v in data.items() if k != "id"}

        # Ensure numeric fields are proper integers before saving
        for field in ["priority", "monthly_target", "max_queries", "max_results", "daily_email_limit"]:
            if field in bucket_data and bucket_data[field] is not None:
                try:
                    bucket_data[field] = int(bucket_data[field])
                except (ValueError, TypeError):
                    logger.warning(f"Invalid value for {field} in bucket {data.get('name')}: {bucket_data[field]}")

        result = db.buckets.find_one_and_update(
            {"name": data["name"]},
            {"$set": bucket_data},
            upsert=True,
            return_document=ReturnDocument.AFTER,
            collation={"locale": "en", "strength": 2},
        )

        if result:
            result["id"] = str(result.pop("_id"))
            logger.debug(f"Saved bucket: {data['name']}")
            return result
        return {}
    except Exception as e:
        logger.error(f"Error saving bucket {data.get('name')}: {e}")
        return {}


def get_all_buckets() -> list[dict[str, Any]]:
    """Get all buckets with all fields.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        buckets = list(db.buckets.find({}))
        return _sanitize_documents(buckets)
    except Exception as e:
        logger.error(f"Error fetching buckets: {e}")
        return []


def count_buckets() -> int:
    """Get total count of buckets.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        return db.buckets.count_documents({})
    except Exception as e:
        logger.error(f"Error counting buckets: {e}")
        return 0


def get_bucket_by_name(name: str) -> dict[str, Any] | None:
    """Get bucket by name using collation for case-insensitive matching.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        bucket = db.buckets.find_one(
            {"name": name},
            collation={"locale": "en", "strength": 2},
        )
        if bucket:
            return _sanitize_document(bucket)
        return None
    except Exception as e:
        logger.error(f"Error fetching bucket {name}: {e}")
        return None


def get_bucket_id_by_name(name: str) -> str | None:
    """Get bucket ID by name."""
    bucket = get_bucket_by_name(name)
    if bucket and bucket.get("id"):
        return bucket["id"]
    return None


def ensure_indexes() -> None:
    """Create MongoDB indexes for frequently queried fields.

    Called once at application startup to ensure optimal query performance.
    Index creation is idempotent — safe to call multiple times.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        db.leads.create_index([("status", ASCENDING)])
        db.leads.create_index([("bucket_id", ASCENDING)])
        db.leads.create_index([("website", ASCENDING)])
        db.leads.create_index([("created_at", DESCENDING)])
        db.leads.create_index([("status", ASCENDING), ("website", ASCENDING)])

        db.email_campaigns.create_index([("status", ASCENDING)])
        db.email_campaigns.create_index([("lead_id", ASCENDING)])
        db.email_campaigns.create_index([("sent_at", DESCENDING)])

        db.query_performance.create_index([("bucket_id", ASCENDING)])
        db.query_performance.create_index([("is_active", ASCENDING)])
        db.query_performance.create_index([("consecutive_failures", ASCENDING)])
        db.query_performance.create_index([("last_executed_at", DESCENDING)])
        db.query_performance.create_index(
            [("is_active", ASCENDING), ("consecutive_failures", ASCENDING)]
        )

        logger.info("Database indexes ensured")
    except Exception as e:
        logger.error(f"Error ensuring indexes: {e}")


def count_pending_audits() -> int:
    """Count leads pending audit (lightweight, no aggregation pipeline).

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        return db.leads.count_documents({"status": "pending_audit", "website": {"$ne": None}})
    except Exception as e:
        logger.error(f"Error counting pending audits: {e}")
        return 0


def count_qualified_leads() -> int:
    """Count qualified leads without emails (lightweight, no aggregation pipeline).

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        qualified_count = db.leads.count_documents({"status": "qualified"})
        if qualified_count == 0:
            return 0

        lead_ids_with_campaigns = set(
            db.email_campaigns.distinct("lead_id", {"status": {"$ne": "needs_review"}})
        )
        return max(0, qualified_count - len(lead_ids_with_campaigns))
    except Exception as e:
        logger.error(f"Error counting qualified leads: {e}")
        return 0


def count_emails_for_review() -> int:
    """Count email campaigns needing review (lightweight, no aggregation pipeline).

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        return db.email_campaigns.count_documents({"status": "needs_review"})
    except Exception as e:
        logger.error(f"Error counting emails for review: {e}")
        return 0



def save_leads_batch(leads: list[dict[str, Any]]) -> int:
    """Save multiple leads in batch.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        bucket_map = {}
        bucket_names = {lead.get("bucket") for lead in leads if lead.get("bucket")}

        if bucket_names:
            for bucket in db.buckets.find({"name": {"$in": list(bucket_names)}}):
                bucket_map[bucket["name"]] = str(bucket["_id"])

        insert_data = []
        for lead_data in leads:
            insert_data.append(
                {
                    "business_name": lead_data.get("business_name"),
                    "category": lead_data.get("category"),
                    "location": lead_data.get("location"),
                    "phone": lead_data.get("phone"),
                    "email": lead_data.get("email"),
                    "website": lead_data.get("website"),
                    "source": lead_data.get("source"),
                    "bucket_id": bucket_map.get(lead_data.get("bucket")),
                    "quality_score": lead_data.get("quality_score", 0.5),
                    "social_links": lead_data.get("social_links", {}),
                    "contact_form_url": lead_data.get("contact_form_url"),
                    "tech_stack": lead_data.get("tech_stack"),
                    "metadata": lead_data.get("metadata", {}),
                    "status": "pending_audit",
                    "created_at": datetime.now(timezone.utc),
                }
            )

        result = db.leads.insert_many(insert_data, ordered=False)
        logger.info(f"Saved {len(result.inserted_ids)} leads in batch")
        return len(result.inserted_ids)
    except Exception as e:
        logger.error(f"Error saving leads batch: {e}")
        for lead in leads:
            queue_pending_write("insert_one", {"collection": "leads", **lead})
        return 0


def get_pending_audits(limit: int = 50) -> list[dict[str, Any]]:
    """Get leads pending audit using aggregation with $lookup.

    Single query replaces N+1 pattern: joins leads with buckets via $lookup.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        pipeline = [
            {"$match": {"status": "pending_audit", "website": {"$ne": None}}},
            {
                "$lookup": {
                    "from": "buckets",
                    "localField": "bucket_id",
                    "foreignField": "_id",
                    "as": "bucket",
                }
            },
            {"$project": {
                "business_name": 1,
                "website": 1,
                "bucket_name": {"$arrayElemAt": ["$bucket.name", 0]},
            }},
            {"$limit": limit},
        ]

        results = list(db.leads.aggregate(pipeline))
        return [
            {
                "id": str(doc["_id"]),
                "business_name": doc["business_name"],
                "website": doc["website"],
                "bucket": doc.get("bucket_name"),
            }
            for doc in results
        ]
    except Exception as e:
        logger.error(f"Error fetching pending audits: {e}")
        return []


def get_qualified_leads(limit: int = 50) -> list[dict[str, Any]]:
    """Get qualified leads without emails using aggregation with $lookup.

    Single query replaces the 2+N pattern:
    - Uses $lookup to join buckets
    - Uses $match to exclude leads with sent emails

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        pipeline = [
            {
                "$lookup": {
                    "from": "email_campaigns",
                    "localField": "_id",
                    "foreignField": "lead_id",
                    "as": "campaigns",
                }
            },
            {"$match": {
                "status": "qualified",
                "campaigns": {"$size": 0},
            }},
            {
                "$lookup": {
                    "from": "buckets",
                    "localField": "bucket_id",
                    "foreignField": "_id",
                    "as": "bucket",
                }
            },
            {"$project": {
                "business_name": 1,
                "website": 1,
                "bucket_name": {"$arrayElemAt": ["$bucket.name", 0]},
                "email": 1,
                "phone": 1,
                "issues_json": 1,
                "audit_score": 1,
            }},
            {"$limit": limit},
        ]

        results = list(db.leads.aggregate(pipeline))
        return [
            {
                "id": str(lead["_id"]),
                "business_name": lead["business_name"],
                "website": lead["website"],
                "bucket": lead.get("bucket_name"),
                "email": lead.get("email"),
                "phone": lead.get("phone"),
                "issues_json": lead.get("issues_json") or [],
                "audit_score": lead.get("audit_score") or 0,
            }
            for lead in results
        ]
    except Exception as e:
        logger.error(f"Error fetching qualified leads: {e}")
        return []


def save_audits_batch(audits: list[dict[str, Any]]) -> int:
    """Save audit results using bulk_write for efficient batch updates.

    Uses PyMongo's bulk_write instead of individual update_one calls in a loop.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        operations = []
        for audit_data in audits:
            try:
                lead_id = audit_data["lead_id"]
                data = audit_data.get("data", {})
                score = data.get("score", 0)
                issues = data.get("issues", [])
                qualified = bool(data.get("qualified", 0))

                oid = _to_object_id(lead_id)
                operations.append(
                    UpdateOne(
                        {"_id": oid},
                        {
                            "$set": {
                                "status": "qualified" if qualified else "unqualified",
                                "audit_score": score,
                                "issues_json": issues,
                            }
                        },
                    )
                )
            except (ValueError, KeyError) as e:
                logger.error(f"Error preparing audit: {e}")
                continue

        if operations:
            result = db.leads.bulk_write(operations, ordered=False)
            logger.info(f"Saved {result.modified_count} audit results")
            return result.modified_count
        return 0
    except Exception as e:
        logger.error(f"Error saving audits batch: {e}")
        return 0



def save_emails_batch(emails: list[dict[str, Any]]) -> int:
    """Save multiple email campaigns.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        insert_data = []
        for email in emails:
            insert_data.append(
                {
                    "lead_id": email.get("lead_id"),
                    "subject": email.get("subject"),
                    "body": email.get("body"),
                    "status": email.get("status", "needs_review"),
                    "duration": email.get("duration"),
                }
            )

        result = db.email_campaigns.insert_many(insert_data)
        logger.info(f"Saved {len(result.inserted_ids)} email campaigns")
        return len(result.inserted_ids)
    except Exception as e:
        logger.error(f"Error saving emails: {e}")
        for email in emails:
            queue_pending_write("insert_one", {"collection": "email_campaigns", **email})
        return 0


def get_emails_for_review(limit: int = 50) -> list[dict[str, Any]]:
    """Get emails needing review using aggregation with $lookup.

    Single query replaces N+1 pattern: joins email_campaigns with leads.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        pipeline = [
            {"$match": {"status": "needs_review"}},
            {
                "$lookup": {
                    "from": "leads",
                    "localField": "lead_id",
                    "foreignField": "_id",
                    "as": "lead",
                }
            },
            {"$match": {"lead": {"$ne": []}}},  
            {"$project": {
                "subject": 1,
                "body": 1,
                "status": 1,
                "duration": 1,
                "business_name": {"$arrayElemAt": ["$lead.business_name", 0]},
                "email": {"$arrayElemAt": ["$lead.email", 0]},
                "social_links": {"$arrayElemAt": ["$lead.social_links", 0]},
                "contact_form_url": {"$arrayElemAt": ["$lead.contact_form_url", 0]},
            }},
            {"$limit": limit},
        ]

        results = list(db.email_campaigns.aggregate(pipeline))
        return [
            {
                "id": str(ec["_id"]),
                "business_name": ec.get("business_name"),
                "email": ec.get("email"),
                "to_email": ec.get("email"),
                "subject": ec["subject"],
                "body": ec["body"],
                "status": ec["status"],
                "lead_id": str(ec["lead_id"]),
                "social_links": ec.get("social_links") or {},
                "contact_form_url": ec.get("contact_form_url"),
                "duration": ec.get("duration"),
            }
            for ec in results
        ]
    except Exception as e:
        logger.error(f"Error fetching emails for review: {e}")
        return []


def update_email_content(campaign_id: str, subject: str, body: str) -> None:
    """Update email content.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        oid = _to_object_id(campaign_id)
        db.email_campaigns.update_one(
            {"_id": oid},
            {"$set": {"subject": subject, "body": body, "status": "approved"}},
        )
        logger.debug(f"Updated email content: {campaign_id}")
    except ValueError as e:
        logger.error(f"Invalid campaign ID: {e}")
    except Exception as e:
        logger.error(f"Error updating email content: {e}")


def delete_email(campaign_id: str) -> None:
    """Delete email campaign.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        oid = _to_object_id(campaign_id)
        db.email_campaigns.delete_one({"_id": oid})
        logger.debug(f"Deleted email campaign: {campaign_id}")
    except ValueError as e:
        logger.error(f"Invalid campaign ID: {e}")
    except Exception as e:
        logger.error(f"Error deleting email campaign: {e}")


def mark_email_sent(
    campaign_id: str,
    lead_id: str | None,
    success: bool,
    error: str | None = None,
    bucket_id: str | None = None,
) -> None:
    """Mark email as sent/failed and update bucket email count.

    Args:
        campaign_id: Email campaign ID
        lead_id: Lead ID (used to find bucket if bucket_id not provided)
        success: Whether the email was sent successfully
        error: Error message if failed
        bucket_id: Optional bucket ID to skip the lead lookup (optimization)

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        oid = _to_object_id(campaign_id)
    except ValueError as e:
        logger.error(f"Invalid campaign ID: {e}")
        return

    try:
        if success:
            now = datetime.now(timezone.utc)
            db.email_campaigns.update_one(
                {"_id": oid},
                {"$set": {"status": "sent", "sent_at": now, "bounce_reason": None}},
            )

            target_bucket_id = bucket_id
            if not target_bucket_id and lead_id:
                try:
                    lead_oid = _to_object_id(lead_id)
                    lead = db.leads.find_one({"_id": lead_oid}, {"bucket_id": 1})
                    if lead:
                        target_bucket_id = lead.get("bucket_id")
                except ValueError:
                    pass

            if target_bucket_id:
                try:
                    bucket_oid = _to_object_id(target_bucket_id)
                    db.buckets.update_one(
                        {"_id": bucket_oid}, {"$inc": {"daily_email_count": 1}}
                    )
                except ValueError:
                    pass
        else:
            db.email_campaigns.update_one(
                {"_id": oid},
                {
                    "$set": {"status": "failed", "bounce_reason": error},
                    "$inc": {"retry_count": 1},
                },
            )
        logger.debug(f"Marked email {campaign_id} as {'sent' if success else 'failed'}")
    except Exception as e:
        logger.error(f"Error marking email sent: {e}")


def get_or_create_query_performance(
    bucket_id: str, query_pattern: str, city: str
) -> dict | None:
    """Get or create query performance tracking record using upsert.

    Uses find_one_and_update with upsert=True to eliminate race condition
    under concurrent access. This replaces the unsafe find_one + insert_one pattern.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

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
            return _sanitize_document(result)
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
    """Update query performance metrics.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

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

        oid = _to_object_id(qp_id)
        db.query_performance.update_one({"_id": oid}, update)
    except ValueError as e:
        logger.error(f"Invalid query performance ID: {e}")
    except Exception as e:
        logger.error(f"Error updating query performance: {e}")


def mark_query_as_stale(qp_id: str) -> None:
    """Mark a query as stale.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        oid = _to_object_id(qp_id)
        db.query_performance.update_one({"_id": oid}, {"$set": {"is_active": False}})
    except ValueError as e:
        logger.error(f"Invalid query performance ID: {e}")
    except Exception as e:
        logger.error(f"Error marking query as stale: {e}")


def get_stale_queries(
    max_failures: int = 3, bucket_id: str | None = None
) -> list[dict]:
    """Get queries that have exceeded failure threshold.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        query: dict = {"is_active": True, "consecutive_failures": {"$gte": max_failures}}
        if bucket_id:
            query["bucket_id"] = bucket_id

        results = list(db.query_performance.find(query))
        return _sanitize_documents(results)
    except Exception as e:
        logger.error(f"Error fetching stale queries: {e}")
        return []


def cleanup_stale_queries(days_threshold: int = 30) -> int:
    """Clean up very old stale queries.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

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


def get_all_leads(limit: int = 1000, cursor: str | None = None) -> list[dict[str, Any]]:
    """Get all leads with cursor-based pagination for better performance.

    Uses range queries on _id instead of skip/limit which degrades with large offsets.

    Args:
        limit: Maximum number of leads to return (default 1000)
        cursor: Optional _id of the last item from previous page

    Returns:
        List of lead dictionaries with next_cursor for pagination
    """
    db = _get_db()


    try:
        query = {}
        if cursor:
            cursor_oid = _to_object_id(cursor)
            query["_id"] = {"$gt": cursor_oid}

        cursor_results = list(db.leads.find(query).sort("_id", 1).limit(limit + 1))
        
        results = []
        for lead in cursor_results[:limit]:
            lead["id"] = str(lead.pop("_id"))
            results.append(lead)

        return results
    except Exception as e:
        logger.error(f"Error fetching all leads: {e}")
        return []


def count_leads() -> int:
    """Get total count of leads.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        return db.leads.count_documents({})
    except Exception as e:
        logger.error(f"Error counting leads: {e}")
        raise


def update_lead_status(lead_id: str, status: str) -> None:
    """Update lead status.

    Raises DatabaseUnavailableError if database is not connected.
    """
    db = _get_db()

    try:
        oid = _to_object_id(lead_id)
        db.leads.update_one({"_id": oid}, {"$set": {"status": status}})
        logger.debug(f"Updated lead status to {status}: {lead_id}")
    except ValueError as e:
        logger.error(f"Invalid lead ID: {e}")
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")



def get_email_campaigns(limit: int = 500) -> list[dict]:
    """Get email campaigns with limit to prevent memory issues."""
    db = _get_db()


    try:
        results = list(db.email_campaigns.find().limit(limit))
        return _sanitize_documents(results)
    except Exception as e:
        logger.error(f"Error fetching email campaigns: {e}")
        return []


def get_query_performance_all() -> list[dict]:
    """Get all query performance records with limit."""
    db = _get_db()


    try:
        results = list(db.query_performance.find().limit(1000))
        return _sanitize_documents(results)
    except Exception as e:
        logger.error(f"Error fetching query performance records: {e}")
        return []
