"""MongoDB Database Connection using PyMongo (sync) — optimized for Streamlit.

Features:
- Connection pooling with configurable limits
- Health check / ping mechanism
- Circuit breaker pattern for resilience
- TTL-based cleanup for pending writes
- Email campaign tracking helpers
- No async/sync bridging needed!
"""

import json
import threading
import time
from pathlib import Path
from enum import Enum
from typing import Any

from pymongo import MongoClient

from core.settings import MONGODB_URI, MONGODB_DATABASE
from core.logging import get_logger

logger = get_logger(__name__)

# ─── Globals ───────────────────────────────────────────────────────────────

_client: MongoClient | None = None
_database: Any | None = None
_db_lock = threading.Lock()
_is_initialized = False
_is_healthy = False

# ─── Circuit Breaker ───────────────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast, not calling MongoDB
    HALF_OPEN = "half_open" # Testing if MongoDB is back

class CircuitBreaker:
    """Simple circuit breaker to prevent hammering a failing MongoDB."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
            return self._state

    def record_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit breaker CLOSED after successful call")

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker OPEN after {self._failure_count} failures"
                )

    def can_execute(self) -> bool:
        return self.state != CircuitState.OPEN

    def reset(self):
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info("Circuit breaker reset to CLOSED")


_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

# ─── Disk-based fallback for when DB is unreachable ────────

_PENDING_WRITES_DIR = Path(__file__).parent.parent / "data" / "pending_writes"
_PENDING_WRITES_DIR.mkdir(parents=True, exist_ok=True)
_pending_writes_lock = threading.Lock()
PENDING_WRITES_TTL_DAYS = 7  # Cleanup writes older than 7 days


# ─── Connection Configuration ──────────────────────────────────────────────

def _create_configured_client() -> MongoClient:
    """Create MongoDB client with production-grade connection pooling."""
    return MongoClient(
        MONGODB_URI,
        maxPoolSize=50,           # Max concurrent connections
        minPoolSize=5,            # Keep minimum connections alive
        maxIdleTimeMS=300000,     # Close idle connections after 5 min
        serverSelectionTimeoutMS=5000,  # Fail fast if unreachable
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        retryWrites=True,         # Auto-retry writes on transient errors
        retryReads=True,          # Auto-retry reads on transient errors
        tls=True,                 # Enforce TLS for security
        tlsAllowInvalidCertificates=False,
        uuidRepresentation="standard",
    )


# ─── Health Check ──────────────────────────────────────────────────────────

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


# ─── Index Creation ────────────────────────────────────────────────────────

def _create_indexes(db: Any) -> None:
    """Create required indexes for collections."""
    # Leads collection
    db.leads.create_index("website", unique=True)
    db.leads.create_index("status")
    db.leads.create_index("bucket_id")
    db.leads.create_index("created_at")

    # Buckets collection
    db.buckets.create_index("name", unique=True)

    # Query performance collection
    db.query_performance.create_index(
        [("bucket_id", 1), ("query_pattern", 1), ("city", 1)], unique=True
    )
    db.query_performance.create_index("is_active")
    db.query_performance.create_index("consecutive_failures")

    # Email campaigns collection
    db.email_campaigns.create_index([("lead_id", 1), ("status", 1)])
    db.email_campaigns.create_index("status")
    db.email_campaigns.create_index("sent_at")

    logger.info("MongoDB indexes created/verified")


# ─── Initialization ────────────────────────────────────────────────────────

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

            # Run index creation
            _create_indexes(_database)

            # Run health check
            health = _ping_database()
            if health:
                logger.info(f"Connected to MongoDB: {MONGODB_DATABASE}")
            else:
                logger.warning("MongoDB connected but health check failed")

            _is_initialized = True
            _circuit_breaker.reset()

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB: {e}")
            _client = None
            _database = None
            _is_initialized = True  # Mark as attempted
            _is_healthy = False


# ─── Public API ────────────────────────────────────────────────────────────

def get_client() -> MongoClient | None:
    """Get the MongoDB client instance."""
    return _client


def get_database() -> Any | None:
    """Get the MongoDB database instance."""
    return _database


def is_connected() -> bool:
    """Check if MongoDB is connected and initialized."""
    return _is_initialized and _database is not None


def get_circuit_breaker_state() -> dict[str, Any]:
    """Get circuit breaker status for monitoring."""
    return {
        "state": _circuit_breaker.state.value,
        "can_execute": _circuit_breaker.can_execute(),
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


# ─── Pending Writes (Disk-based Fallback) ──────────────────────────────────

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
            with open(write_file, "w") as f:
                json.dump(write_entry, f)
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

                collection_name = entry["data"].pop("collection", None)
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


# ─── Email Campaign Helper Functions ───────────────────────────────────────

def get_email_campaign_stats() -> dict[str, Any]:
    """Get overall email campaign statistics.
    
    Returns:
        Dictionary with campaign metrics (total, sent, pending, failed, etc.)
    """
    if not is_connected():
        return {}
    
    try:
        db = _database
        total = db.email_campaigns.count_documents({})
        sent = db.email_campaigns.count_documents({"status": "sent"})
        pending = db.email_campaigns.count_documents({"status": "needs_review"})
        failed = db.email_campaigns.count_documents({"status": "failed"})
        approved = db.email_campaigns.count_documents({"status": "approved"})
        
        return {
            "total": total,
            "sent": sent,
            "pending_review": pending,
            "failed": failed,
            "approved": approved,
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
        return db.email_campaigns.count_documents({})
    except Exception as e:
        logger.error(f"Error counting email campaigns: {e}")
        return 0
