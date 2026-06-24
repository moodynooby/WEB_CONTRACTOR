"""Email campaign repository — CRUD + stats for email campaigns."""

from datetime import datetime, timezone
from typing import Any

from database._helpers import get_db, to_object_id
from infra.logging import get_logger

logger = get_logger(__name__)


def save_emails_batch(emails: list[dict[str, Any]]) -> int:
    """Save multiple email campaigns."""
    db = get_db()

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
        return 0


def get_emails_for_review(limit: int = 50) -> list[dict[str, Any]]:
    """Get emails needing review using aggregation with $lookup."""
    db = get_db()

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
            {
                "$project": {
                    "subject": 1,
                    "body": 1,
                    "status": 1,
                    "duration": 1,
                    "business_name": {"$arrayElemAt": ["$lead.business_name", 0]},
                    "email": {"$arrayElemAt": ["$lead.email", 0]},
                    "social_links": {"$arrayElemAt": ["$lead.social_links", 0]},
                    "contact_form_url": {"$arrayElemAt": ["$lead.contact_form_url", 0]},
                }
            },
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
    """Update email content."""
    db = get_db()

    try:
        oid = to_object_id(campaign_id)
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
    db = get_db()

    try:
        oid = to_object_id(campaign_id)
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
    """Mark email as sent/failed and update bucket email count."""
    db = get_db()

    try:
        oid = to_object_id(campaign_id)
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
                    lead_oid = to_object_id(lead_id)
                    lead = db.leads.find_one({"_id": lead_oid}, {"bucket_id": 1})
                    if lead:
                        target_bucket_id = lead.get("bucket_id")
                except ValueError:
                    pass

            if target_bucket_id:
                try:
                    bucket_oid = to_object_id(target_bucket_id)
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


def count_emails_for_review() -> int:
    """Count email campaigns needing review."""
    db = get_db()

    try:
        return db.email_campaigns.count_documents({"status": "needs_review"})
    except Exception as e:
        logger.error(f"Error counting emails for review: {e}")
        return 0


# --- Stats (moved from connection.py) ---


def get_email_campaign_stats() -> dict[str, Any]:
    """Get overall email campaign statistics using single aggregation pipeline."""
    from database.connection import is_connected

    if not is_connected():
        return {}

    try:
        db = get_db()

        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                }
            }
        ]

        status_counts = {}
        for doc in db.email_campaigns.aggregate(pipeline):
            status_counts[doc["_id"]] = doc["count"]

        total = sum(status_counts.values())
        sent = status_counts.get("sent", 0)

        return {
            "total": total,
            "sent": sent,
            "pending_review": status_counts.get("needs_review", 0),
            "failed": status_counts.get("failed", 0),
            "approved": status_counts.get("approved", 0),
            "success_rate": round((sent / total * 100) if total > 0 else 0, 2),
        }
    except Exception as e:
        logger.error(f"Error getting email campaign stats: {e}")
        return {}


def get_recent_email_campaigns(limit: int = 50) -> list[dict]:
    """Get recent email campaigns sorted by creation time."""
    from database.connection import is_connected

    if not is_connected():
        return []

    try:
        db = get_db()
        campaigns = list(db.email_campaigns.find().sort("sent_at", -1).limit(limit))
        for campaign in campaigns:
            campaign["id"] = str(campaign.pop("_id"))
        return campaigns
    except Exception as e:
        logger.error(f"Error fetching recent email campaigns: {e}")
        return []


def count_email_campaigns() -> int:
    """Get total count of email campaigns."""
    from database.connection import is_connected

    if not is_connected():
        return 0

    try:
        db = get_db()
        return db.email_campaigns.count_documents({})
    except Exception as e:
        logger.error(f"Error counting email campaigns: {e}")
        return 0
