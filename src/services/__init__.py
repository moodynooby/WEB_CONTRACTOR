"""Service Layer - decoupled form/business logic for Web Contractor.

Framework-agnostic services used by both Streamlit UI and any future interfaces.
"""

from services.email_service import EmailService
from services.bucket_service import BucketService
from services.pipeline_service import PipelineService
from services.stats_service import StatsService

__all__ = ["EmailService", "BucketService", "PipelineService", "StatsService"]
