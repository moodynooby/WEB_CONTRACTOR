"""Lead repository — CRUD + batch operations for leads."""

from datetime import datetime, timezone
from typing import Any

from pymongo import UpdateOne

from database._helpers import get_db, to_object_id, sanitize_document
from infra.logging import get_logger

logger = get_logger(__name__)


def save_leads_batch(leads: list[dict[str, Any]]) -> int:
    """Save multiple leads in batch, skipping duplicates."""
    db = get_db()

    try:
        bucket_map = {}
        bucket_names = {lead.get("bucket") for lead in leads if lead.get("bucket")}

        if bucket_names:
            for bucket in db.buckets.find({"name": {"$in": list(bucket_names)}}):
                bucket_map[bucket["name"]] = str(bucket["_id"])

        operations = []
        for lead_data in leads:
            lead_doc = {
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

            operations.append(
                UpdateOne(
                    {"website": lead_data.get("website")},
                    {"$setOnInsert": lead_doc},
                    upsert=True,
                )
            )

        if not operations:
            return 0

        result = db.leads.bulk_write(operations, ordered=False)
        logger.info(
            f"Saved {result.upserted_count} leads, skipped {result.matched_count} duplicates"
        )
        return result.upserted_count
    except Exception as e:
        logger.error(f"Error saving leads batch: {e}")
        return 0


def get_pending_audits(limit: int = 50) -> list[dict[str, Any]]:
    """Get leads pending audit using aggregation with $lookup."""
    db = get_db()

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
            {
                "$project": {
                    "business_name": 1,
                    "website": 1,
                    "bucket_name": {"$arrayElemAt": ["$bucket.name", 0]},
                }
            },
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
    """Get qualified leads without emails using aggregation with $lookup."""
    db = get_db()

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
            {
                "$match": {
                    "status": "qualified",
                    "campaigns": {"$size": 0},
                }
            },
            {
                "$lookup": {
                    "from": "buckets",
                    "localField": "bucket_id",
                    "foreignField": "_id",
                    "as": "bucket",
                }
            },
            {
                "$project": {
                    "business_name": 1,
                    "website": 1,
                    "bucket_name": {"$arrayElemAt": ["$bucket.name", 0]},
                    "email": 1,
                    "phone": 1,
                    "issues_json": 1,
                    "audit_score": 1,
                }
            },
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


def get_lead_by_id(lead_id: str) -> dict[str, Any] | None:
    """Fetch a single lead document by its string ID."""
    db = get_db()

    try:
        oid = to_object_id(lead_id)
        lead = db.leads.find_one({"_id": oid})
        if lead is None:
            return None
        return sanitize_document(lead)
    except ValueError as e:
        logger.error(f"Invalid lead ID: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching lead: {e}")
        return None


def count_leads_pending_audit() -> int:
    """Count leads pending audit."""
    db = get_db()

    try:
        return db.leads.count_documents(
            {"status": "pending_audit", "website": {"$ne": None}}
        )
    except Exception as e:
        logger.error(f"Error counting pending audits: {e}")
        return 0


def count_qualified_leads_without_emails() -> int:
    """Count qualified leads without emails."""
    db = get_db()

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


def save_audits_batch(audits: list[dict[str, Any]]) -> int:
    """Save audit results using bulk_write for efficient batch updates."""
    db = get_db()

    try:
        operations = []
        for audit_data in audits:
            try:
                lead_id = audit_data["lead_id"]
                data = audit_data.get("data", {})
                score = data.get("score", 0)
                issues = data.get("issues", [])
                qualified = bool(data.get("qualified", 0))

                oid = to_object_id(lead_id)
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


def count_leads() -> int:
    """Get total count of leads."""
    db = get_db()

    try:
        return db.leads.count_documents({})
    except Exception as e:
        logger.error(f"Error counting leads: {e}")
        raise


def update_lead_status(lead_id: str, status: str) -> None:
    """Update lead status."""
    db = get_db()

    try:
        oid = to_object_id(lead_id)
        db.leads.update_one({"_id": oid}, {"$set": {"status": status}})
        logger.debug(f"Updated lead status to {status}: {lead_id}")
    except ValueError as e:
        logger.error(f"Invalid lead ID: {e}")
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
