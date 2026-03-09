"""Peewee ORM Models for Web Contractor

Pure model definitions only - no business logic.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from peewee import (  # type: ignore[import-untyped]
    Model,
    SqliteDatabase,
    TextField,
    IntegerField,
    FloatField,
    BooleanField,
    DateTimeField,
    ForeignKeyField,
    Check,
)

db = SqliteDatabase(
    'leads.db',
    thread_safe=True,
    pragmas={
        'journal_mode': 'wal',
        'foreign_keys': 'on',
        'synchronous': 'NORMAL',
        'cache_size': -64000,
        'temp_store': 'memory',
    }
)


class BaseModel(Model):
    class Meta:
        database = db
        legacy_table_names = False


class Bucket(BaseModel):
    name = TextField(unique=True)
    categories = TextField(null=True)
    search_patterns = TextField(null=True)
    geographic_segments = TextField(null=True)
    intent_profile = TextField(null=True)
    conversion_probability = FloatField(default=0.0)
    monthly_target = IntegerField(default=0)
    daily_email_count = IntegerField(default=0)
    last_reset_date = DateTimeField(default=lambda: datetime.now().date())
    daily_email_limit = IntegerField(default=500)
    max_queries = IntegerField(default=5)
    max_results = IntegerField(default=2)
    priority = IntegerField(default=1)

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'categories': json.loads(self.categories) if self.categories else [],
            'search_patterns': json.loads(self.search_patterns) if self.search_patterns else [],
            'geographic_segments': json.loads(self.geographic_segments) if self.geographic_segments else [],
            'intent_profile': self.intent_profile,
            'conversion_probability': self.conversion_probability,
            'monthly_target': self.monthly_target,
            'daily_email_count': self.daily_email_count,
            'daily_email_limit': self.daily_email_limit,
            'max_queries': self.max_queries,
            'max_results': self.max_results,
            'priority': self.priority,
        }


class Lead(BaseModel):
    business_name = TextField()
    category = TextField(null=True)
    location = TextField(null=True)
    phone = TextField(null=True)
    email = TextField(null=True)
    website = TextField(unique=True)
    source = TextField(null=True)
    status = TextField(default='pending_audit')
    quality_score = FloatField(default=0.5)
    bucket = ForeignKeyField(Bucket, backref='leads', null=True, on_delete='SET NULL')
    created_at = DateTimeField(default=datetime.now)
    last_email_sent_at = DateTimeField(null=True)
    social_links = TextField(null=True)
    contact_form_url = TextField(null=True)

    class Meta:
        indexes = (
            (('status',), False),
            (('bucket_id',), False),
        )

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'business_name': self.business_name,
            'category': self.category,
            'location': self.location,
            'phone': self.phone,
            'email': self.email,
            'website': self.website,
            'source': self.source,
            'status': self.status,
            'quality_score': self.quality_score,
            'bucket': self.bucket.name if self.bucket else None,
            'bucket_id': self.bucket_id,
            'social_links': json.loads(self.social_links) if self.social_links else {},
            'contact_form_url': self.contact_form_url,
        }


class Audit(BaseModel):
    lead = ForeignKeyField(Lead, backref='audits', on_delete='CASCADE')
    url = TextField(null=True)
    score = IntegerField(default=0)
    issues_json = TextField(null=True)
    qualified = BooleanField(default=False)
    duration = FloatField(null=True)
    audit_date = DateTimeField(default=datetime.now)

    class Meta:
        indexes = (
            (('qualified',), False),
            (('lead_id',), False),
        )

    def get_issues(self) -> List[Dict]:
        return json.loads(self.issues_json) if self.issues_json else []


class AuditIssue(BaseModel):
    audit = ForeignKeyField(Audit, backref='issues', on_delete='CASCADE')
    issue_type = TextField()
    severity = TextField(constraints=[Check("severity IN ('critical', 'warning', 'info')")])
    description = TextField(null=True)

    class Meta:
        indexes = (
            (('audit_id',), False),
            (('issue_type',), False),
        )


class EmailCampaign(BaseModel):
    lead = ForeignKeyField(Lead, backref='emails', on_delete='CASCADE')
    subject = TextField()
    body = TextField()
    status = TextField(default='pending')
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
            (('status',), False),
            (('lead_id', 'status'), False),
        )


class AppConfig(BaseModel):
    key = TextField(primary_key=True)
    value = TextField(null=True)

    def get_value(self) -> Optional[Dict]:
        return json.loads(self.value) if self.value else None

    def set_value(self, value: Dict) -> None:
        self.value = json.dumps(value)
        self.save()


class QueryPerformance(BaseModel):
    """Track query performance to identify and disable stale queries"""
    bucket = ForeignKeyField(Bucket, backref='query_performances', on_delete='CASCADE')
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
            (('bucket_id', 'query_pattern', 'city'), True),
            (('is_active',), False),
            (('consecutive_failures',), False),
        )

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'bucket': self.bucket.name if self.bucket else None,
            'bucket_id': self.bucket_id,
            'query_pattern': self.query_pattern,
            'city': self.city,
            'is_active': self.is_active,
            'total_executions': self.total_executions,
            'total_leads_found': self.total_leads_found,
            'total_leads_saved': self.total_leads_saved,
            'total_qualified': self.total_qualified,
            'consecutive_failures': self.consecutive_failures,
            'last_executed_at': self.last_executed_at.isoformat() if self.last_executed_at else None,
            'created_at': self.created_at.isoformat(),
        }
