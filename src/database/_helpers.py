"""Shared database helpers — ObjectId conversion, document sanitization, DB access."""

from typing import Any

from bson import ObjectId
from database.connection import get_database, DatabaseUnavailableError
from infra.logging import get_logger

logger = get_logger(__name__)


def get_db():
    """Get the database instance. Raises DatabaseUnavailableError if unavailable."""
    db = get_database()
    if db is None:
        raise DatabaseUnavailableError(
            "Database is not connected. Check MONGODB_URI configuration."
        )
    return db


def to_object_id(id_str: str) -> ObjectId:
    """Convert string ID to ObjectId safely."""
    if isinstance(id_str, ObjectId):
        return id_str
    try:
        return ObjectId(id_str)
    except Exception:
        raise ValueError(f"Invalid ObjectId: {id_str}")


def sanitize_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB document to API-friendly format."""
    result = doc.copy()
    result["id"] = str(result.pop("_id"))
    return result


def sanitize_documents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize a list of documents."""
    return [sanitize_document(doc) for doc in docs]
