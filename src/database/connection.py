"""MongoDB Database Connection using PyMongo (sync) — production-ready.

Features:
- Connection pooling with configurable limits
- Health check / ping mechanism
- TTL-based cleanup for pending writes
- Email campaign tracking helpers
- No async/sync bridging needed!
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from infra.settings import MONGODB_URI, MONGODB_DATABASE
from infra.logging import get_logger

logger = get_logger(__name__)


class DatabaseUnavailableError(Exception):
    """Raised when a database operation is attempted but the DB is unavailable.

    Unlike returning empty lists/zeros, this makes it explicit to callers
    that the database is down so they can show proper error messages.
    """
    pass


_client: MongoClient | None = None
_database: Any | None = None
_db_lock = threading.Lock()
_is_initialized = False
_is_healthy = False


_PENDING_WRITES_DIR = Path(__file__).parent.parent / "data" / "pending_writes"
_PENDING_WRITES_DIR.mkdir(parents=True, exist_ok=True)
_pending_writes_lock = threading.Lock()
PENDING_WRITES_TTL_DAYS = 7

logger.debug(f"Pending writes directory: {_PENDING_WRITES_DIR}")


def is_initialized() -> bool:
    """Check if the database has been initialized (attempted connection).

    This is True even if the connection attempt failed.
    Use is_connected() to check if the DB is actually available.
    """
    return _is_initialized  



def _create_configured_client() -> MongoClient:
    """Create MongoDB client with production-grade connection pooling."""
    return MongoClient(
        MONGODB_URI,
        maxPoolSize=50,           
        minPoolSize=5,            
        maxIdleTimeMS=300000,     
        serverSelectionTimeoutMS=5000,  
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        retryWrites=True,         
        retryReads=True,          
        tls=True,                 
        tlsAllowInvalidCertificates=False,
        uuidRepresentation="standard",
    )



def _ping_database() -> bool:
    """Check if MongoDB is reachable with a ping command."""
    global _is_healthy
    try:
        if _database is None:
            return False
        _database.command("ping")
        _is_healthy = True
        return True
    except Exception as e:
        _is_healthy = False
        logger.warning(f"MongoDB ping failed: {e}")
        return False


def is_healthy() -> bool:
    """Check if MongoDB connection is healthy."""
    return _is_healthy and _database is not None



def _create_indexes(db: Any) -> None:
    """Create required indexes for collections."""
    db.leads.create_index("website", unique=True)
    db.leads.create_index("status")
    db.leads.create_index("bucket_id")
    db.leads.create_index("created_at")

    db.leads.create_index([("status", 1), ("website", 1)])
    db.leads.create_index([("status", 1), ("bucket_id", 1)])
    db.leads.create_index([("status", 1), ("created_at", -1)])

    try:
        existing_indexes = db.buckets.list_indexes()
        for idx in existing_indexes:
            if idx.get("key") == {"name": 1}:
                if not idx.get("collation"):
                    db.buckets.drop_index(idx["name"])
                    logger.info(f"Dropped old index '{idx['name']}' from buckets collection")
                break
    except Exception as e:
        logger.warning(f"Error checking buckets indexes: {e}")

    db.buckets.create_index(
        "name",
        unique=True,
        collation={"locale": "en", "strength": 2},
    )

    db.query_performance.create_index(
        [("bucket_id", 1), ("query_pattern", 1), ("city", 1)], unique=True
    )
    db.query_performance.create_index("is_active")
    db.query_performance.create_index("consecutive_failures")
    db.query_performance.create_index(
        "last_executed_at", expireAfterSeconds=2592000
    )  

    db.email_campaigns.create_index([("lead_id", 1), ("status", 1)])
    db.email_campaigns.create_index("status")
    db.email_campaigns.create_index([("status", 1), ("sent_at", -1)])
    
    try:
        db.email_campaigns.create_index(
            "sent_at", expireAfterSeconds=7776000
        )
    except Exception as e:
        if "IndexOptionsConflict" in str(e) or "already exists" in str(e):
            db.email_campaigns.drop_index("sent_at_1")
            db.email_campaigns.create_index(
                "sent_at", expireAfterSeconds=7776000
            )
        else:
            raise  

    logger.info("MongoDB indexes created/verified")



def init_db() -> None:
    """Initialize MongoDB connection and create indexes (thread-safe, idempotent)."""
    global _client, _database, _is_initialized

    with _db_lock:
        if _is_initialized:
            logger.debug("Database already initialized, skipping")
            return

        if not MONGODB_URI:
            logger.warning("MONGODB_URI not set. Database disabled.")
            _is_initialized = True
            return

        try:
            logger.info("Initializing MongoDB connection...")
            _client = _create_configured_client()
            _database = _client[MONGODB_DATABASE]

            _create_indexes(_database)

            health = _ping_database()
            if health:
                logger.info(f"Connected to MongoDB: {MONGODB_DATABASE}")
            else:
                logger.warning("MongoDB connected but health check failed")

            _is_initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB: {e}")
            _client = None
            _database = None
            _is_initialized = True  
            _is_healthy = False



def get_client() -> MongoClient | None:
    """Get the MongoDB client instance."""
    return _client


def get_database() -> Any | None:
    """Get the MongoDB database instance."""
    return _database


def is_connected() -> bool:
    """Check if MongoDB is connected and initialized."""
    return _is_initialized and _database is not None


def get_connection_status() -> dict[str, Any]:
    """Get database connection status for UI display.

    Returns:
        Dict with connected, healthy, and database name info.
    """
    from infra.settings import MONGODB_DATABASE

    return {
        "connected": _is_initialized and _database is not None,
        "healthy": _is_healthy,
        "database": MONGODB_DATABASE if _database is not None else None,
    }


def close_db() -> None:
    """Close MongoDB connection."""
    global _client, _database, _is_initialized, _is_healthy
    with _db_lock:
        if _client:
            try:
                _client.close()
                logger.info("MongoDB connection closed")
            except Exception as e:
                logger.error(f"Error closing MongoDB: {e}")
            finally:
                _client = None
                _database = None
                _is_initialized = False
                _is_healthy = False



def queue_pending_write(operation: str, data: dict) -> None:
    """Queue a database write to disk when DB is unreachable.

    Args:
        operation: One of 'insert_one', 'insert_many', 'update_one', 'delete_one'
        data: Dict with 'collection' key and operation-specific data
    """
    with _pending_writes_lock:
        timestamp = time.time()
        write_entry = {
            "timestamp": timestamp,
            "operation": operation,
            "data": data,
        }
        write_file = _PENDING_WRITES_DIR / f"write_{timestamp}.json"
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(_PENDING_WRITES_DIR), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as tmp_f:
                    json.dump(write_entry, tmp_f)
                os.replace(tmp_path, str(write_file))
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
            logger.warning(f"Queued pending write to disk: {write_file.name}")
        except Exception as e:
            logger.error(f"Failed to queue pending write: {e}")


def flush_pending_writes() -> int:
    """Retry all pending disk writes when DB connection is restored.

    Returns:
        Number of successfully flushed writes
    """
    if not is_connected():
        logger.warning("Cannot flush pending writes: DB not connected")
        return 0

    with _pending_writes_lock:
        write_files = sorted(_PENDING_WRITES_DIR.glob("write_*.json"))
        if not write_files:
            return 0

        flushed = 0
        for write_file in write_files:
            try:
                with open(write_file) as f:
                    entry = json.load(f)

                db = _database
                if db is None:
                    break

                collection_name = entry["data"].get("collection")
                if not collection_name:
                    continue

                collection = db[collection_name]
                operation = entry["operation"]
                data = entry["data"]

                if operation == "insert_one":
                    collection.insert_one(data)
                elif operation == "insert_many":
                    collection.insert_many(data.get("documents", []), ordered=False)
                elif operation == "update_one":
                    collection.update_one(data.get("filter", {}), data.get("update", {}))
                elif operation == "delete_one":
                    collection.delete_one(data.get("filter", {}))
                else:
                    logger.warning(f"Unknown operation: {operation}")
                    continue

                write_file.unlink()
                flushed += 1
                logger.info(f"Flushed pending write: {write_file.name}")

            except Exception as e:
                logger.error(f"Failed to flush pending write {write_file.name}: {e}")

        if flushed > 0:
            logger.info(f"Flushed {flushed} pending writes to DB")

        return flushed


def cleanup_old_pending_writes(max_age_days: int = PENDING_WRITES_TTL_DAYS) -> int:
    """Remove pending writes older than TTL to prevent disk bloat.

    Returns:
        Number of cleaned up files
    """
    with _pending_writes_lock:
        cutoff_time = time.time() - (max_age_days * 86400)
        cleaned = 0

        for write_file in _PENDING_WRITES_DIR.glob("write_*.json"):
            try:
                file_mtime = write_file.stat().st_mtime
                if file_mtime < cutoff_time:
                    write_file.unlink()
                    cleaned += 1
                    logger.debug(f"Cleaned up old pending write: {write_file.name}")
            except Exception as e:
                logger.error(f"Failed to cleanup pending write {write_file.name}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old pending writes (> {max_age_days} days)")

        return cleaned



def get_email_campaign_stats() -> dict[str, Any]:
    """Get overall email campaign statistics using single aggregation pipeline.

    Uses MongoDB's $group to count by status in one query instead of 5 separate calls.
    """
    if not is_connected():
        return {}

    try:
        db = _database
        if db is None:
            return {}

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
    """Get recent email campaigns sorted by creation time.

    Args:
        limit: Maximum number of campaigns to return

    Returns:
        List of campaign dictionaries
    """
    if not is_connected():
        return []

    try:
        db = _database
        if db is None:
            return []
        campaigns = list(
            db.email_campaigns.find()
            .sort("sent_at", -1)
            .limit(limit)
        )
        for campaign in campaigns:
            campaign["id"] = str(campaign.pop("_id"))
        return campaigns
    except Exception as e:
        logger.error(f"Error fetching recent email campaigns: {e}")
        return []


def count_email_campaigns() -> int:
    """Get total count of email campaigns."""
    if not is_connected():
        return 0

    try:
        db = _database
        if db is None:
            return 0
        return db.email_campaigns.count_documents({})
    except Exception as e:
        logger.error(f"Error counting email campaigns: {e}")
        return 0
