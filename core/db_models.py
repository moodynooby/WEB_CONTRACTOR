"""Peewee ORM Models for Web Contractor.

Pure model definitions only - no business logic.
"""

from datetime import datetime
from typing import Any, Dict

from peewee import (
    BooleanField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)
from playhouse.sqlite_ext import JSONField

from core.settings import DB_PATH

db = SqliteDatabase(
    DB_PATH,
    thread_safe=True,
    pragmas={
        "journal_mode": "wal",
        "foreign_keys": "on",
        "synchronous": "NORMAL",
        "cache_size": -64000,
        "temp_store": "memory",
    },
)


class BaseModel(Model):
    """Base model with common serialization."""

    class Meta:
        database = db
        legacy_table_names = False

    def to_dict(self, recurse: bool = True) -> Dict[str, Any]:
        """Convert model to dictionary.

        Args:
            recurse: If True, serialize foreign key references.

        Returns:
            Dictionary representation of the model.
        """
        data: Dict[str, Any] = {}
        for field in self._meta.fields.values():
            value = getattr(self, field.name)

            if isinstance(field, JSONField):
                data[field.name] = value if value else {}

            elif isinstance(field, DateTimeField) and value:
                data[field.name] = value.isoformat() if value else None

            elif isinstance(field, ForeignKeyField) and value and recurse:
                data[field.name] = value.to_dict()
                data[f"{field.name}_id"] = getattr(self, f"{field.name}_id")
            else:
                data[field.name] = value

        return data


class Bucket(BaseModel):
    """Bucket for categorizing leads and queries."""

    name = TextField(unique=True)
    categories = JSONField(null=True)
    search_patterns = JSONField(null=True)
    geographic_segments = JSONField(null=True)
    intent_profile = TextField(null=True)
    conversion_probability = FloatField(default=0.0)
    monthly_target = IntegerField(default=0)
    daily_email_count = IntegerField(default=0)
    last_reset_date = DateTimeField(default=lambda: datetime.now().date())
    daily_email_limit = IntegerField(default=500)
    max_queries = IntegerField(default=5)
    max_results = IntegerField(default=2)
    priority = IntegerField(default=1)

    def to_dict(self, recurse: bool = True) -> Dict[str, Any]:
        """Convert bucket to dictionary."""
        data = super().to_dict(recurse)
        data["categories"] = self.categories or []
        data["search_patterns"] = self.search_patterns or []
        data["geographic_segments"] = self.geographic_segments or []
        return data


class Lead(BaseModel):
    """Lead representing a potential customer."""

    business_name = TextField()
    category = TextField(null=True)
    location = TextField(null=True)
    phone = TextField(null=True)
    email = TextField(null=True)
    website = TextField(unique=True)
    source = TextField(null=True)
    status = TextField(default="pending_audit")
    quality_score = FloatField(default=0.5)
    audit_score = IntegerField(default=0)
    issues_json = JSONField(null=True)
    bucket = ForeignKeyField(Bucket, backref="leads", null=True, on_delete="SET NULL")
    created_at = DateTimeField(default=datetime.now)
    last_email_sent_at = DateTimeField(null=True)
    social_links = JSONField(null=True)
    contact_form_url = TextField(null=True)
    tech_stack = TextField(null=True)
    metadata = JSONField(null=True)

    class Meta:
        indexes = ((("status",), False), (("bucket_id",), False))

    def to_dict(self, recurse: bool = True) -> Dict[str, Any]:
        """Convert lead to dictionary."""
        data = super().to_dict(recurse)
        data["social_links"] = self.social_links or {}
        data["bucket"] = self.bucket.name if self.bucket else None
        return data


class EmailCampaign(BaseModel):
    """Email campaign for outreach."""

    lead = ForeignKeyField(Lead, backref="emails", on_delete="CASCADE")
    subject = TextField()
    body = TextField()
    status = TextField(default="pending")
    duration = FloatField(null=True)
    sent_at = DateTimeField(null=True)
    opened_at = DateTimeField(null=True)
    clicked_at = DateTimeField(null=True)
    replied_at = DateTimeField(null=True)
    bounce_reason = TextField(null=True)
    retry_count = IntegerField(default=0)
    next_retry_at = DateTimeField(null=True)
    max_retries = IntegerField(default=3)

    class Meta:
        indexes = (
            (("status",), False),
            (("lead_id", "status"), False),
        )


class QueryPerformance(BaseModel):
    """Track query performance to identify and disable stale queries."""

    bucket = ForeignKeyField(Bucket, backref="query_performances", on_delete="CASCADE")
    query_pattern = TextField()
    city = TextField()
    is_active = BooleanField(default=True)
    total_executions = IntegerField(default=0)
    total_leads_found = IntegerField(default=0)
    total_leads_saved = IntegerField(default=0)
    total_qualified = IntegerField(default=0)
    consecutive_failures = IntegerField(default=0)
    last_executed_at = DateTimeField(null=True)
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        indexes = (
            (("bucket_id", "query_pattern", "city"), True),
            (("is_active",), False),
            (("consecutive_failures",), False),
        )

    def to_dict(self, recurse: bool = True) -> Dict[str, Any]:
        """Convert query performance to dictionary."""
        data = super().to_dict(recurse)
        data["bucket"] = self.bucket.name if self.bucket else None
        if self.last_executed_at:
            data["last_executed_at"] = self.last_executed_at.isoformat()
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        return data
