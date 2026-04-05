"""Repository Layer for MongoDB operations - Sync version for Streamlit.

Uses PyMongo directly (no async wrappers needed!).

Features:
- TTL-based caching for frequently accessed data
- Pagination support for large collections
- Better error handling with explicit logging
- Projection to limit returned fields
"""

from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from cachetools import TTLCache

from core.db import get_database, queue_pending_write
from core.logging import get_logger

logger = get_logger(__name__)

# ─── Caching Layer ─────────────────────────────────────────────────────────

# Cache buckets for 5 minutes (they rarely change)
_bucket_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
_bucket_name_to_id_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


def _get_db():
    """Get the database instance from db module."""
    return get_database()


def _to_object_id(id_str: str) -> ObjectId:
    """Convert string ID to ObjectId safely."""
    if isinstance(id_str, ObjectId):
        return id_str
    try:
        return ObjectId(id_str)
    except Exception:
        raise ValueError(f"Invalid ObjectId: {id_str}")


# ─── Bucket Operations ─────────────────────────────────────────────────────

def save_bucket(data: dict[str, Any]) -> dict[str, Any]:
    """Save or update bucket. Returns the saved bucket data with id."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return {}

    try:
        bucket_data = {k: v for k, v in data.items() if k != "id"}

        existing = db.buckets.find_one({"name": data["name"]})
        if existing:
            db.buckets.update_one({"name": data["name"]}, {"$set": bucket_data})
            bucket_data["id"] = str(existing["_id"])
            logger.debug(f"Updated bucket: {data['name']}")
        else:
            result = db.buckets.insert_one(bucket_data)
            bucket_data["id"] = str(result.inserted_id)
            logger.debug(f"Created bucket: {data['name']}")

        # Invalidate cache
        _bucket_cache.pop(data.get("name"), None)
        _bucket_name_to_id_cache.pop(data.get("name"), None)

        return bucket_data
    except Exception as e:
        logger.error(f"Error saving bucket {data.get('name')}: {e}")
        return {}


def get_all_buckets() -> list[dict[str, Any]]:
    """Get all buckets."""
    db = _get_db()
    if db is None:
        return []

    try:
        buckets = []
        for bucket in db.buckets.find():
            bucket["id"] = str(bucket.pop("_id"))
            buckets.append(bucket)
        return buckets
    except Exception as e:
        logger.error(f"Error fetching buckets: {e}")
        return []


def get_bucket_by_name(name: str) -> dict[str, Any] | None:
    """Get bucket by name with caching."""
    # Check cache first
    if name in _bucket_cache:
        return _bucket_cache[name]

    db = _get_db()
    if db is None:
        return None

    try:
        bucket = db.buckets.find_one({"name": name})
        if bucket:
            bucket["id"] = str(bucket.pop("_id"))
            _bucket_cache[name] = bucket
        return bucket
    except Exception as e:
        logger.error(f"Error fetching bucket {name}: {e}")
        return None


def get_bucket_id_by_name(name: str) -> str | None:
    """Get bucket ID by name with caching."""
    if name in _bucket_name_to_id_cache:
        return _bucket_name_to_id_cache[name]

    bucket = get_bucket_by_name(name)
    if bucket and bucket.get("id"):
        _bucket_name_to_id_cache[name] = bucket["id"]
        return bucket["id"]
    return None


# ─── Lead Operations ───────────────────────────────────────────────────────

def save_lead(data: dict[str, Any]) -> str:
    """Save single lead. Returns lead ID as string or empty string on error."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        # Queue for later when DB is back
        queue_pending_write("insert_one", {"collection": "leads", **data})
        return ""

    try:
        lead_data = {
            "business_name": data.get("business_name"),
            "category": data.get("category"),
            "location": data.get("location"),
            "phone": data.get("phone"),
            "email": data.get("email"),
            "website": data.get("website"),
            "source": data.get("source"),
            "bucket_id": data.get("bucket_id"),
            "quality_score": data.get("quality_score", 0.5),
            "social_links": data.get("social_links", {}),
            "contact_form_url": data.get("contact_form_url"),
            "tech_stack": data.get("tech_stack"),
            "metadata": data.get("metadata", {}),
            "status": data.get("status", "pending_audit"),
            "created_at": datetime.now(),
        }

        result = db.leads.insert_one(lead_data)
        logger.debug(f"Saved lead: {data.get('business_name')}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Error saving lead: {e}")
        # Queue for later
        queue_pending_write("insert_one", {"collection": "leads", **data})
        return ""


def save_leads_batch(leads: list[dict[str, Any]]) -> int:
    """Save multiple leads in batch."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        # Queue each lead for later
        for lead in leads:
            queue_pending_write("insert_one", {"collection": "leads", **lead})
        return 0

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
                    "created_at": datetime.now(),
                }
            )

        result = db.leads.insert_many(insert_data, ordered=False)
        logger.info(f"Saved {len(result.inserted_ids)} leads in batch")
        return len(result.inserted_ids)
    except Exception as e:
        logger.error(f"Error saving leads batch: {e}")
        # Queue each lead for later
        for lead in leads:
            queue_pending_write("insert_one", {"collection": "leads", **lead})
        return 0


def update_lead_contact_info(lead_id: str, info: dict[str, Any]) -> None:
    """Update lead contact info."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return

    update_data = {}

    if info.get("email"):
        update_data["email"] = info["email"]
    if info.get("phone"):
        update_data["phone"] = info["phone"]
    if "social_links" in info:
        update_data["social_links"] = info["social_links"]
    if "contact_form_url" in info:
        update_data["contact_form_url"] = info["contact_form_url"]
    if "tech_stack" in info:
        update_data["tech_stack"] = info["tech_stack"]
    if "metadata" in info:
        update_data["metadata"] = info["metadata"]

    if update_data:
        try:
            oid = _to_object_id(lead_id)
            db.leads.update_one({"_id": oid}, {"$set": update_data})
            logger.debug(f"Updated lead contact info: {lead_id}")
        except ValueError as e:
            logger.error(f"Invalid lead ID: {e}")
        except Exception as e:
            logger.error(f"Error updating lead contact info: {e}")


def get_pending_audits(limit: int = 50) -> list[dict[str, Any]]:
    """Get leads pending audit with projection to limit fields."""
    db = _get_db()
    if db is None:
        return []

    try:
        results = []
        # Use projection to only fetch needed fields
        for lead in db.leads.find(
            {"status": "pending_audit", "website": {"$ne": None}},
            {"business_name": 1, "website": 1, "bucket_id": 1}
        ).limit(limit):
            bucket = None
            if lead.get("bucket_id"):
                try:
                    bucket_oid = _to_object_id(lead["bucket_id"])
                    bucket = db.buckets.find_one({"_id": bucket_oid}, {"name": 1})
                except ValueError:
                    pass
            results.append(
                {
                    "id": str(lead["_id"]),
                    "business_name": lead["business_name"],
                    "website": lead["website"],
                    "bucket": bucket["name"] if bucket else None,
                }
            )
        return results
    except Exception as e:
        logger.error(f"Error fetching pending audits: {e}")
        return []


def get_qualified_leads(limit: int = 50) -> list[dict[str, Any]]:
    """Get qualified leads without emails with projection."""
    db = _get_db()
    if db is None:
        return []

    try:
        sent_lead_ids = set()
        for ec in db.email_campaigns.find({}, {"lead_id": 1}):
            if ec.get("lead_id"):
                sent_lead_ids.add(str(ec["lead_id"]))

        query = {"status": "qualified"}
        if sent_lead_ids:
            query["_id"] = {"$nin": [_to_object_id(lid) for lid in sent_lead_ids if lid]}

        results = []
        # Use projection to limit fields
        for lead in db.leads.find(
            query,
            {
                "business_name": 1,
                "website": 1,
                "bucket_id": 1,
                "email": 1,
                "phone": 1,
                "issues_json": 1,
                "audit_score": 1,
            }
        ).limit(limit):
            bucket = None
            if lead.get("bucket_id"):
                try:
                    bucket_oid = _to_object_id(lead["bucket_id"])
                    bucket = db.buckets.find_one({"_id": bucket_oid}, {"name": 1})
                except ValueError:
                    pass
            results.append(
                {
                    "id": str(lead["_id"]),
                    "business_name": lead["business_name"],
                    "website": lead["website"],
                    "bucket": bucket["name"] if bucket else None,
                    "email": lead.get("email"),
                    "phone": lead.get("phone"),
                    "issues_json": lead.get("issues_json") or [],
                    "audit_score": lead.get("audit_score") or 0,
                }
            )
        return results
    except Exception as e:
        logger.error(f"Error fetching qualified leads: {e}")
        return []


def save_audits_batch(audits: list[dict[str, Any]]) -> int:
    """Save audit results to Lead table."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return 0

    saved = 0
    for audit_data in audits:
        try:
            lead_id = audit_data["lead_id"]
            data = audit_data.get("data", {})
            score = data.get("score", 0)
            issues = data.get("issues", [])
            qualified = bool(data.get("qualified", 0))

            oid = _to_object_id(lead_id)
            db.leads.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": "qualified" if qualified else "unqualified",
                        "audit_score": score,
                        "issues_json": issues,
                    }
                },
            )
            saved += 1
        except (ValueError, KeyError) as e:
            logger.error(f"Error saving audit: {e}")
            continue

    logger.info(f"Saved {saved} audit results")
    return saved


# ─── Email Campaign Operations ─────────────────────────────────────────────

def save_emails_batch(emails: list[dict[str, Any]]) -> int:
    """Save multiple email campaigns."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        for email in emails:
            queue_pending_write("insert_one", {"collection": "email_campaigns", **email})
        return 0

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
    """Get emails needing review with projection."""
    db = _get_db()
    if db is None:
        return []

    try:
        results = []

        for ec in db.email_campaigns.find(
            {"status": "needs_review"},
            {"lead_id": 1, "subject": 1, "body": 1, "status": 1, "duration": 1}
        ).limit(limit):
            lead = None
            if ec.get("lead_id"):
                try:
                    lead_oid = _to_object_id(ec["lead_id"])
                    lead = db.leads.find_one(
                        {"_id": lead_oid},
                        {"business_name": 1, "email": 1, "social_links": 1, "contact_form_url": 1}
                    )
                except ValueError:
                    pass
            if lead:
                results.append(
                    {
                        "id": str(ec["_id"]),
                        "business_name": lead["business_name"],
                        "email": lead.get("email"),
                        "subject": ec["subject"],
                        "body": ec["body"],
                        "status": ec["status"],
                        "lead_id": str(ec["lead_id"]),
                        "social_links": lead.get("social_links") or {},
                        "contact_form_url": lead.get("contact_form_url"),
                        "duration": ec.get("duration"),
                    }
                )
        return results
    except Exception as e:
        logger.error(f"Error fetching emails for review: {e}")
        return []


def update_email_content(campaign_id: str, subject: str, body: str) -> None:
    """Update email content."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return

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
    """Delete email campaign."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return

    try:
        oid = _to_object_id(campaign_id)
        db.email_campaigns.delete_one({"_id": oid})
        logger.debug(f"Deleted email campaign: {campaign_id}")
    except ValueError as e:
        logger.error(f"Invalid campaign ID: {e}")
    except Exception as e:
        logger.error(f"Error deleting email campaign: {e}")


def mark_email_sent(campaign_id: str, success: bool, error: str | None = None) -> None:
    """Mark email as sent."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return

    try:
        oid = _to_object_id(campaign_id)
    except ValueError as e:
        logger.error(f"Invalid campaign ID: {e}")
        return

    try:
        if success:
            now = datetime.now()
            db.email_campaigns.update_one(
                {"_id": oid},
                {"$set": {"status": "sent", "sent_at": now, "bounce_reason": None}},
            )

            campaign = db.email_campaigns.find_one({"_id": oid}, {"lead_id": 1})
            if campaign and campaign.get("lead_id"):
                try:
                    lead_oid = _to_object_id(campaign["lead_id"])
                    lead = db.leads.find_one({"_id": lead_oid}, {"bucket_id": 1})
                    if lead and lead.get("bucket_id"):
                        bucket_oid = _to_object_id(lead["bucket_id"])
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


# ─── Query Performance Operations ──────────────────────────────────────────

def get_or_create_query_performance(
    bucket_id: str, query_pattern: str, city: str
) -> dict | None:
    """Get or create query performance tracking record."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return None

    try:
        existing = db.query_performance.find_one(
            {
                "bucket_id": bucket_id,
                "query_pattern": query_pattern,
                "city": city,
            }
        )

        if existing:
            existing["id"] = str(existing.pop("_id"))
            return existing

        new_qp = {
            "bucket_id": bucket_id,
            "query_pattern": query_pattern,
            "city": city,
            "is_active": True,
            "total_executions": 0,
            "total_leads_found": 0,
            "total_leads_saved": 0,
            "total_qualified": 0,
            "consecutive_failures": 0,
            "created_at": datetime.now(),
        }

        result = db.query_performance.insert_one(new_qp)
        new_qp["id"] = str(result.inserted_id)
        return new_qp
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
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return

    try:
        update = {
            "$inc": {
                "total_executions": 1,
                "total_leads_found": leads_found,
                "total_leads_saved": leads_saved,
                "total_qualified": qualified_count,
            },
            "$set": {"last_executed_at": datetime.now()},
        }

        if success and leads_found > 0:
            update["$set"]["consecutive_failures"] = 0
        else:
            update["$inc"]["consecutive_failures"] = 1

        oid = _to_object_id(qp_id)
        db.query_performance.update_one({"_id": oid}, update)
    except ValueError as e:
        logger.error(f"Invalid query performance ID: {e}")
    except Exception as e:
        logger.error(f"Error updating query performance: {e}")


def mark_query_as_stale(qp_id: str) -> None:
    """Mark a query as stale."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return

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
    """Get queries that have exceeded failure threshold."""
    db = _get_db()
    if db is None:
        return []

    try:
        query = {"is_active": True, "consecutive_failures": {"$gte": max_failures}}
        if bucket_id:
            query["bucket_id"] = bucket_id

        results = []
        for qp in db.query_performance.find(query):
            qp["id"] = str(qp.pop("_id"))
            results.append(qp)
        return results
    except Exception as e:
        logger.error(f"Error fetching stale queries: {e}")
        return []


def cleanup_stale_queries(days_threshold: int = 30) -> int:
    """Clean up very old stale queries."""
    db = _get_db()
    if db is None:
        return 0

    try:
        cutoff_date = datetime.now() - timedelta(days=days_threshold)

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


def get_query_performance_stats(bucket_id: str | None = None) -> dict[str, Any]:
    """Get overall query performance statistics."""
    db = _get_db()
    if db is None:
        return {}

    try:
        query = {}
        if bucket_id:
            query["bucket_id"] = bucket_id

        total_queries = db.query_performance.count_documents(query)
        active_queries = db.query_performance.count_documents({**query, "is_active": True})
        stale_queries = db.query_performance.count_documents(
            {**query, "is_active": True, "consecutive_failures": {"$gte": 3}}
        )

        pipeline = [
            {"$match": query} if query else {"$match": {}},
            {
                "$group": {
                    "_id": None,
                    "total_executions": {"$sum": "$total_executions"},
                    "total_leads": {"$sum": "$total_leads_found"},
                    "total_qualified": {"$sum": "$total_qualified"},
                }
            },
        ]

        agg = list(db.query_performance.aggregate(pipeline))

        if agg:
            stats = agg[0]
            avg_success = (
                (stats["total_leads"] / stats["total_executions"] * 100)
                if stats["total_executions"] > 0
                else 0
            )
        else:
            stats = {"total_executions": 0, "total_leads": 0, "total_qualified": 0}
            avg_success = 0

        return {
            "total_queries": total_queries,
            "active_queries": active_queries,
            "stale_queries": stale_queries,
            "total_executions": stats["total_executions"],
            "total_leads_found": stats["total_leads"],
            "total_qualified": stats["total_qualified"],
            "average_success_rate": round(avg_success, 2),
        }
    except Exception as e:
        logger.error(f"Error getting query performance stats: {e}")
        return {}


# ─── Generic Lead Operations ───────────────────────────────────────────────

def get_all_leads(limit: int = 1000, skip: int = 0) -> list[dict]:
    """Get all leads with pagination to prevent memory issues.
    
    Args:
        limit: Maximum number of leads to return (default 1000)
        skip: Number of leads to skip for pagination
    
    Returns:
        List of lead dictionaries
    """
    db = _get_db()
    if db is None:
        return []

    try:
        results = []
        for lead in db.leads.find().skip(skip).limit(limit):
            lead["id"] = str(lead.pop("_id"))
            results.append(lead)
        return results
    except Exception as e:
        logger.error(f"Error fetching all leads: {e}")
        return []


def count_leads() -> int:
    """Get total count of leads."""
    db = _get_db()
    if db is None:
        return 0

    try:
        return db.leads.count_documents({})
    except Exception as e:
        logger.error(f"Error counting leads: {e}")
        return 0


def update_lead_status(lead_id: str, status: str) -> None:
    """Update lead status."""
    db = _get_db()
    if db is None:
        logger.error("Database not initialized")
        return

    try:
        oid = _to_object_id(lead_id)
        db.leads.update_one({"_id": oid}, {"$set": {"status": status}})
        logger.debug(f"Updated lead status to {status}: {lead_id}")
    except ValueError as e:
        logger.error(f"Invalid lead ID: {e}")
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")


# ─── Email Campaign Queries ────────────────────────────────────────────────

def get_email_campaigns(limit: int = 500) -> list[dict]:
    """Get email campaigns with limit to prevent memory issues."""
    db = _get_db()
    if db is None:
        return []

    try:
        results = []
        for campaign in db.email_campaigns.find().limit(limit):
            campaign["id"] = str(campaign.pop("_id"))
            results.append(campaign)
        return results
    except Exception as e:
        logger.error(f"Error fetching email campaigns: {e}")
        return []


def get_query_performance_all() -> list[dict]:
    """Get all query performance records with limit."""
    db = _get_db()
    if db is None:
        return []

    try:
        results = []
        for qp in db.query_performance.find().limit(1000):
            qp["id"] = str(qp.pop("_id"))
            results.append(qp)
        return results
    except Exception as e:
        logger.error(f"Error fetching query performance records: {e}")
        return []
