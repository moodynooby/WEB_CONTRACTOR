"""Data models using dataclasses for MongoDB documents.

Provides dataclass definitions for:
- Bucket: Search bucket configuration
- Lead: Discovered business leads
- EmailCampaign: Outbound email campaigns
- QueryPerformance: Query execution tracking
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional


@dataclass
class SearchBucket:
    name: str
    categories: list[str] = field(default_factory=list)
    search_patterns: list[str] = field(default_factory=list)
    geographic_segments: list[str] = field(default_factory=list)
    intent_profile: str = ""
    conversion_probability: float = 0.0
    monthly_target: int = 0
    daily_email_count: int = 0
    last_reset_date: datetime = field(default_factory=datetime.now)
    daily_email_limit: int = 500
    max_queries: int = 5
    max_results: int = 2
    priority: int = 1
    _id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("_id"):
            data["id"] = str(data.pop("_id"))
        else:
            data.pop("_id", None)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SearchBucket":
        if "_id" in data and data["_id"]:
            data["_id"] = str(data["_id"])
        return cls(**data)


@dataclass
class Lead:
    business_name: str
    website: str
    category: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    status: str = "pending_audit"
    quality_score: float = 0.5
    audit_score: int = 0
    issues_json: list[dict] = field(default_factory=list)
    bucket_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_email_sent_at: Optional[datetime] = None
    social_links: dict[str, str] = field(default_factory=dict)
    contact_form_url: Optional[str] = None
    tech_stack: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("_id"):
            data["id"] = str(data.pop("_id"))
        else:
            data.pop("_id", None)
        if data.get("created_at"):
            data["created_at"] = (
                data["created_at"].isoformat()
                if isinstance(data["created_at"], datetime)
                else data["created_at"]
            )
        if data.get("last_email_sent_at"):
            data["last_email_sent_at"] = (
                data["last_email_sent_at"].isoformat()
                if isinstance(data["last_email_sent_at"], datetime)
                else data["last_email_sent_at"]
            )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        if "_id" in data and data["_id"]:
            data["_id"] = str(data["_id"])
        return cls(**data)


@dataclass
class EmailCampaign:
    lead_id: str
    subject: str
    body: str
    status: str = "pending"
    duration: Optional[float] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    bounce_reason: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None
    max_retries: int = 3
    _id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("_id"):
            data["id"] = str(data.pop("_id"))
        else:
            data.pop("_id", None)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "EmailCampaign":
        if "_id" in data and data["_id"]:
            data["_id"] = str(data["_id"])
        return cls(**data)


@dataclass
class QueryPerformance:
    bucket_id: str
    query_pattern: str
    city: str
    is_active: bool = True
    total_executions: int = 0
    total_leads_found: int = 0
    total_leads_saved: int = 0
    total_qualified: int = 0
    consecutive_failures: int = 0
    last_executed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    _id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("_id"):
            data["id"] = str(data.pop("_id"))
        else:
            data.pop("_id", None)
        if data.get("created_at"):
            data["created_at"] = (
                data["created_at"].isoformat()
                if isinstance(data["created_at"], datetime)
                else data["created_at"]
            )
        if data.get("last_executed_at"):
            data["last_executed_at"] = (
                data["last_executed_at"].isoformat()
                if isinstance(data["last_executed_at"], datetime)
                else data["last_executed_at"]
            )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "QueryPerformance":
        if "_id" in data and data["_id"]:
            data["_id"] = str(data["_id"])
        return cls(**data)
