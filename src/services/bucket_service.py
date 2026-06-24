"""Bucket service - decoupled bucket management operations.

Extracted from BucketManager in repository.py.
Provides all bucket CRUD + validation as framework-agnostic methods.
"""

from database.repository import BucketManager
from infra.logging import get_logger

logger = get_logger(__name__)


class BucketService:
    """Bucket management operations, decoupled from any UI framework."""

    @staticmethod
    def create(business_type: str, target_locations: list[str], max_queries: int = 10, max_results: int = 50) -> tuple[bool, str]:
        success, message = BucketManager.create(
            business_type=business_type,
            target_locations=target_locations,
            max_queries=max_queries,
            max_results=max_results,
        )
        if success:
            logger.info(f"Bucket created: {business_type}")
        else:
            logger.warning(f"Bucket creation failed: {message}")
        return success, message

    @staticmethod
    def list() -> list[dict]:
        return BucketManager.list()

    @staticmethod
    def get_by_name(name: str) -> dict | None:
        return BucketManager.get_by_name(name)

    @staticmethod
    def delete(bucket_id: str, cascade: bool = True) -> tuple[bool, str]:
        success, message = BucketManager.delete(bucket_id, cascade=cascade)
        if success:
            logger.info(f"Bucket deleted: {bucket_id}")
        else:
            logger.warning(f"Bucket deletion failed: {message}")
        return success, message
