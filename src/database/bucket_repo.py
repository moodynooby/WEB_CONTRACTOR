"""Bucket repository — CRUD + validation for bucket configurations."""

from typing import Any

from pymongo import ReturnDocument

from database._helpers import get_db, sanitize_document, sanitize_documents
from infra.logging import get_logger

logger = get_logger(__name__)


def save_bucket(data: dict[str, Any]) -> dict[str, Any]:
    """Save or update bucket. Returns the saved bucket data with id."""
    db = get_db()

    try:
        bucket_data = {k: v for k, v in data.items() if k != "id"}

        for field in [
            "priority",
            "monthly_target",
            "max_queries",
            "max_results",
            "daily_email_limit",
        ]:
            if field in bucket_data and bucket_data[field] is not None:
                try:
                    bucket_data[field] = int(bucket_data[field])
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid value for {field} in bucket {data.get('name')}: {bucket_data[field]}"
                    )

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
    """Get all buckets with all fields."""
    db = get_db()

    try:
        buckets = list(db.buckets.find({}))
        return sanitize_documents(buckets)
    except Exception as e:
        logger.error(f"Error fetching buckets: {e}")
        return []


def count_buckets() -> int:
    """Get total count of buckets."""
    db = get_db()

    try:
        return db.buckets.count_documents({})
    except Exception as e:
        logger.error(f"Error counting buckets: {e}")
        return 0


def get_bucket_by_name(name: str) -> dict[str, Any] | None:
    """Get bucket by name using collation for case-insensitive matching."""
    db = get_db()

    try:
        bucket = db.buckets.find_one(
            {"name": name},
            collation={"locale": "en", "strength": 2},
        )
        if bucket:
            return sanitize_document(bucket)
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


def delete_bucket(bucket_id: str, cascade: bool = True) -> tuple[bool, str]:
    """Delete a bucket and optionally cascade delete related data."""
    from database._helpers import to_object_id

    db = get_db()

    try:
        oid = to_object_id(bucket_id)
    except Exception as e:
        return (False, f"Invalid bucket ID: {e}")

    try:
        bucket = db.buckets.find_one({"_id": oid})
        if not bucket:
            return (False, f"Bucket not found with ID: {bucket_id}")

        bucket_name = bucket.get("name", "unknown")

        if cascade:
            leads_result = db.leads.delete_many({"bucket_id": oid})
            logger.info(
                f"Deleted {leads_result.deleted_count} leads for bucket '{bucket_name}'"
            )

            qp_result = db.query_performance.delete_many({"bucket_id": oid})
            logger.info(
                f"Deleted {qp_result.deleted_count} query performance records for bucket '{bucket_name}'"
            )

        result = db.buckets.delete_one({"_id": oid})

        if result.deleted_count > 0:
            msg = f"Bucket '{bucket_name}' deleted successfully"
            if cascade:
                msg += f" ({leads_result.deleted_count} leads, {qp_result.deleted_count} query records removed)"
            logger.info(msg)
            return (True, msg)
        else:
            return (False, f"Failed to delete bucket '{bucket_name}'")

    except Exception as e:
        logger.error(f"Error deleting bucket: {e}")
        return (False, f"Error deleting bucket: {e}")


class BucketManager:
    """Unified bucket management — CRUD + AI-powered config generation."""

    @staticmethod
    def create(
        business_type: str,
        target_locations: list[str],
        max_queries: int = 10,
        max_results: int = 50,
    ) -> tuple[bool, str]:
        from infra.llm import generate_bucket_config

        if not business_type:
            return (False, "Business type is required")
        if not target_locations:
            return (False, "At least one target location is required")

        try:
            config = generate_bucket_config(
                business_type=business_type,
                target_locations=target_locations,
                max_queries=max_queries,
                max_results=max_results,
            )
        except Exception as e:
            return (False, f"LLM generation failed: {e}")

        is_valid, errors = BucketManager.validate(config)
        if not is_valid:
            return (False, f"Validation failed: {'; '.join(errors)}")

        return BucketManager._save(config)

    @staticmethod
    def validate(config: dict[str, Any]) -> tuple[bool, list[str]]:
        errors = []

        if not config.get("name"):
            errors.append("Bucket name is required")
        elif len(config["name"]) < 3:
            errors.append("Bucket name must be at least 3 characters")
        elif len(config["name"]) > 50:
            errors.append("Bucket name must be less than 50 characters")

        if not config.get("categories"):
            errors.append("At least one category is required")
        elif len(config["categories"]) > 10:
            errors.append("Maximum 10 categories allowed")

        if not config.get("search_patterns"):
            errors.append("At least one search pattern is required")
        elif len(config["search_patterns"]) > 20:
            errors.append("Maximum 20 search patterns allowed")

        if not config.get("geographic_segments"):
            errors.append("At least one geographic segment is required")

        if config.get("priority") and not (1 <= config["priority"] <= 5):
            errors.append("Priority must be between 1 and 5")

        if config.get("monthly_target", 0) < 0:
            errors.append("Monthly target must be non-negative")

        if config.get("max_queries", 0) <= 0:
            errors.append("Max queries must be greater than 0")

        if config.get("max_results", 0) <= 0:
            errors.append("Max results must be greater than 0")

        if config.get("daily_email_limit", 0) <= 0:
            errors.append("Daily email limit must be greater than 0")

        return (len(errors) == 0, errors)

    @staticmethod
    def list() -> list[dict[str, Any]]:
        return get_all_buckets()

    @staticmethod
    def get_by_name(name: str) -> dict[str, Any] | None:
        return get_bucket_by_name(name)

    @staticmethod
    def delete(bucket_id: str, cascade: bool = True) -> tuple[bool, str]:
        return delete_bucket(bucket_id, cascade=cascade)

    @staticmethod
    def _save(config: dict[str, Any]) -> tuple[bool, str]:
        from database.connection import is_connected

        if not is_connected():
            return (
                False,
                "Database not connected. Please configure MONGODB_URI in your .env file.",
            )

        existing = get_bucket_by_name(config["name"])
        if existing:
            return (False, f"Bucket '{config['name']}' already exists")

        result = save_bucket(config)
        if result and result.get("id"):
            return (True, f"Bucket '{config['name']}' created successfully")
        return (False, "Failed to save bucket to database")
