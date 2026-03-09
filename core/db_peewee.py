"""Simplified Peewee ORM Models for Web Contractor

Uses Peewee's native functions for maximum simplicity.
No repository pattern - direct model access.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

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
    IntegrityError,
    DatabaseError,
    JOIN,
    prefetch,
)
from playhouse.migrate import SqliteMigrator, migrate  # type: ignore[import-untyped]

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



def init_db():
    """Initialize database and create tables"""
    db.connect(reuse_if_open=True)
    db.create_tables([Bucket, Lead, Audit, AuditIssue, EmailCampaign, AppConfig, QueryPerformance], safe=True)
    _migrate_bucket_columns()


def _migrate_bucket_columns():
    """Add new columns to Bucket table if they don't exist using Peewee migrate."""
    migrator = SqliteMigrator(db)
    
    try:
        migrate(
            migrator.add_column('bucket', 'max_queries', IntegerField(default=5)),
        )
    except Exception:
        pass  
    
    try:
        migrate(
            migrator.add_column('bucket', 'max_results', IntegerField(default=2)),
        )
    except Exception:
        pass  
    
    try:
        migrate(
            migrator.add_column('bucket', 'priority', IntegerField(default=1)),
        )
    except Exception:
        pass  


def close_db():
    """Close database connection"""
    if not db.is_closed():
        db.close()


def save_bucket(data: Dict) -> Any:
    """Save or update bucket"""
    bucket_data = data.copy()
    for key in ['categories', 'search_patterns', 'geographic_segments']:
        if key in bucket_data and isinstance(bucket_data[key], list):
            bucket_data[key] = json.dumps(bucket_data[key])

    bucket, created = Bucket.get_or_create(name=bucket_data['name'], defaults=bucket_data)
    if not created:
        for key, value in bucket_data.items():
            if key != 'name' and hasattr(bucket, key):
                setattr(bucket, key, value)
        bucket.save()
    return bucket  # type: ignore[no-any-return]


def get_all_buckets() -> List[Dict]:
    """Get all buckets"""
    return [b.to_dict() for b in Bucket.select()]


def get_bucket_id_by_name(name: str) -> Optional[int]:
    """Get bucket ID by name"""
    bucket = Bucket.get_or_none(Bucket.name == name)
    return bucket.id if bucket else None  # type: ignore[no-any-return]


def save_config(key: str, value: Dict) -> Any:
    """Save config"""
    config, _ = AppConfig.get_or_create(key=key)
    config.set_value(value)
    return config  # type: ignore[no-any-return]


def get_config(key: str) -> Optional[Dict]:
    """Get config"""
    config = AppConfig.get_or_none(key=key)
    return config.get_value() if config else None


def save_lead(data: Dict) -> int:
    """Save single lead, return ID or -1 on error"""
    try:
        bucket_id = get_bucket_id_by_name(data.get('bucket'))  # type: ignore[arg-type]
        lead = Lead.create(
            business_name=data.get('business_name'),
            category=data.get('category'),
            location=data.get('location'),
            phone=data.get('phone'),
            email=data.get('email'),
            website=data.get('website'),
            source=data.get('source'),
            bucket_id=bucket_id,
            quality_score=data.get('quality_score', 0.5),
            social_links=json.dumps(data.get('social_links', {})),
            contact_form_url=data.get('contact_form_url'),
        )
        return lead.id  # type: ignore[no-any-return]
    except (IntegrityError, DatabaseError):
        return -1


def save_leads_batch(leads: List[Dict]) -> int:
    """Save multiple leads in batch"""
    if not leads:
        return 0

    bucket_map = {}
    bucket_names = {lead.get('bucket') for lead in leads if lead.get('bucket')}
    for b in Bucket.select().where(Bucket.name.in_(bucket_names)):
        bucket_map[b.name] = b.id

    insert_data = []
    for lead_data in leads:
        insert_data.append({
            'business_name': lead_data.get('business_name'),
            'category': lead_data.get('category'),
            'location': lead_data.get('location'),
            'phone': lead_data.get('phone'),
            'email': lead_data.get('email'),
            'website': lead_data.get('website'),
            'source': lead_data.get('source'),
            'bucket_id': bucket_map.get(lead_data.get('bucket')),
            'quality_score': lead_data.get('quality_score', 0.5),
            'social_links': json.dumps(lead_data.get('social_links', {})),
            'contact_form_url': lead_data.get('contact_form_url'),
        })

    try:
        with db.atomic():
            Lead.insert_many(insert_data).execute()
        return len(insert_data)
    except (IntegrityError, DatabaseError):
        return 0


def update_lead_contact_info(lead_id: int, info: Dict) -> None:
    """Update lead contact info"""
    update_data = {}
    if 'email' in info and info['email']:
        update_data['email'] = info['email']
    if 'phone' in info and info['phone']:
        update_data['phone'] = info['phone']
    if 'social_links' in info:
        update_data['social_links'] = json.dumps(info['social_links'])
    if 'contact_form_url' in info:
        update_data['contact_form_url'] = info['contact_form_url']
    
    if update_data:
        Lead.update(**update_data).where(Lead.id == lead_id).execute()


def get_pending_audits(limit: int = 50) -> List[Dict]:
    """Get leads pending audit"""
    query = (Lead
             .select(Lead, Bucket)
             .join(Bucket, on=(Lead.bucket_id == Bucket.id), join_type=JOIN.LEFT_OUTER)
             .where((Lead.status == 'pending_audit') & (Lead.website.is_null(False)))
             .limit(limit))

    return [{
        'id': lead.id,
        'business_name': lead.business_name,
        'website': lead.website,
        'bucket': lead.bucket.name if lead.bucket else None,
    } for lead in query]


def save_audits_batch(audits: List[Dict]) -> int:
    """Save multiple audits"""
    if not audits:
        return 0
    
    saved = 0
    with db.atomic():
        for audit_data in audits:
            try:
                lead_id = audit_data['lead_id']
                data = audit_data.get('data', {})
                duration = audit_data.get('duration')
                
                audit = Audit.create(
                    lead_id=lead_id,
                    url=data.get('url'),
                    score=data.get('score', 0),
                    issues_json=json.dumps(data.get('issues', [])),
                    qualified=bool(data.get('qualified', 0)),
                    duration=duration,
                )
                
                for issue in data.get('issues', []):
                    AuditIssue.create(
                        audit_id=audit.id,
                        issue_type=issue.get('type', 'unknown'),
                        severity=issue.get('severity', 'info'),
                        description=issue.get('description', ''),
                    )
                
                Lead.update(status='qualified' if data.get('qualified') else 'unqualified').where(Lead.id == lead_id).execute()
                saved += 1
            except Exception:
                continue
    return saved


def get_qualified_leads(limit: int = 50) -> List[Dict]:
    """Get qualified leads without emails"""
    already_sent = EmailCampaign.select(EmailCampaign.lead_id)
    query = (Lead
             .select(Lead, Bucket)
             .join(Bucket, on=(Lead.bucket_id == Bucket.id), join_type=JOIN.LEFT_OUTER)
             .where(
                 (Lead.status == 'qualified') &
                 (Lead.id.not_in(already_sent))
             )
             .limit(limit))
    
    leads_with_audits = prefetch(query, Audit)

    result = []
    for lead in leads_with_audits:
        latest_audit = lead.audits[0] if lead.audits else None
        result.append({
            'id': lead.id,
            'business_name': lead.business_name,
            'website': lead.website,
            'bucket': lead.bucket.name if lead.bucket else None,
            'issues_json': latest_audit.issues_json if latest_audit and latest_audit.issues_json else '[]',
        })
    return result


def save_emails_batch(emails: List[Dict]) -> int:
    """Save multiple emails"""
    if not emails:
        return 0
    
    saved = 0
    with db.atomic():
        for email in emails:
            try:
                EmailCampaign.create(
                    lead_id=email.get('lead_id'),
                    subject=email.get('subject'),
                    body=email.get('body'),
                    status=email.get('status', 'needs_review'),
                    duration=email.get('duration'),
                )
                saved += 1
            except Exception:
                continue
    return saved


def get_emails_for_review(limit: int = 50) -> List[Dict]:
    """Get emails needing review"""
    query = (EmailCampaign
             .select(EmailCampaign, Lead)
             .join(Lead, on=(EmailCampaign.lead_id == Lead.id))
             .where(EmailCampaign.status == 'needs_review')
             .limit(limit))

    return [{
        'id': ec.id,
        'business_name': ec.lead.business_name,
        'email': ec.lead.email,
        'subject': ec.subject,
        'body': ec.body,
        'lead_id': ec.lead_id,
        'social_links': json.loads(ec.lead.social_links) if ec.lead.social_links else {},
        'contact_form_url': ec.lead.contact_form_url,
    } for ec in query]


def update_email_content(campaign_id: int, subject: str, body: str) -> None:
    """Update email content"""
    EmailCampaign.update(
        subject=subject,
        body=body,
        status='pending'
    ).where(EmailCampaign.id == campaign_id).execute()


def delete_email(campaign_id: int) -> None:
    """Delete email"""
    EmailCampaign.delete().where(EmailCampaign.id == campaign_id).execute()


def mark_email_sent(campaign_id: int, success: bool, error: Optional[str] = None) -> None:
    """Mark email as sent"""
    with db.atomic():
        if success:
            now = datetime.now()
            EmailCampaign.update(
                status='sent',
                sent_at=now,
                bounce_reason=None
            ).where(EmailCampaign.id == campaign_id).execute()

            campaign = EmailCampaign.get_by_id(campaign_id)
            lead = Lead.get_by_id(campaign.lead_id)
            if lead.bucket_id:
                Bucket.update(
                    daily_email_count=Bucket.daily_email_count + 1
                ).where(Bucket.id == lead.bucket_id).execute()
        else:
            EmailCampaign.update(
                status='failed',
                bounce_reason=error,
                retry_count=EmailCampaign.retry_count + 1,
            ).where(
                (EmailCampaign.id == campaign_id) &
                (EmailCampaign.retry_count < EmailCampaign.max_retries)
            ).execute()

            EmailCampaign.update(
                status='permanently_failed'
            ).where(
                (EmailCampaign.id == campaign_id) &
                (EmailCampaign.retry_count >= EmailCampaign.max_retries)
            ).execute()



def get_or_create_query_performance(bucket_id: int, query_pattern: str, city: str) -> QueryPerformance:
    """Get or create query performance tracking record"""
    try:
        qp, created = QueryPerformance.get_or_create(
            bucket_id=bucket_id,
            query_pattern=query_pattern,
            city=city,
            defaults={'is_active': True}
        )
        return qp  # type: ignore[no-any-return]
    except Exception:
        return QueryPerformance.create(
            bucket_id=bucket_id,
            query_pattern=query_pattern,
            city=city,
            is_active=True
        )


def update_query_performance(
    query_perf: QueryPerformance,
    leads_found: int,
    leads_saved: int,
    qualified_count: int = 0,
    success: bool = True
) -> None:
    """Update query performance metrics after execution"""
    with db.atomic():
        query_perf.total_executions += 1
        query_perf.total_leads_found += leads_found
        query_perf.total_leads_saved += leads_saved
        query_perf.total_qualified += qualified_count
        query_perf.last_executed_at = datetime.now()
        
        if success and leads_found > 0:
            query_perf.consecutive_failures = 0
        else:
            query_perf.consecutive_failures += 1
        
        query_perf.save()


def mark_query_as_stale(query_perf: QueryPerformance) -> None:
    """Mark a query as stale (inactive)"""
    QueryPerformance.update(is_active=False).where(
        QueryPerformance.id == query_perf.id
    ).execute()


def get_stale_queries(max_failures: int = 3, bucket_id: Optional[int] = None) -> List[Dict]:
    """Get queries that have exceeded the failure threshold"""
    query = QueryPerformance.select(QueryPerformance, Bucket).join(
        Bucket, on=(QueryPerformance.bucket_id == Bucket.id), join_type=JOIN.LEFT_OUTER
    ).where(
        QueryPerformance.is_active &
        (QueryPerformance.consecutive_failures >= max_failures)
    )

    if bucket_id:
        query = query.where(QueryPerformance.bucket_id == bucket_id)

    return [qp.to_dict() for qp in query]


def get_query_performance_stats(bucket_id: Optional[int] = None) -> Dict:
    """Get overall query performance statistics"""
    query = QueryPerformance.select()
    if bucket_id:
        query = query.where(QueryPerformance.bucket_id == bucket_id)

    total_queries = query.count()
    active_queries = query.where(QueryPerformance.is_active).count()
    stale_queries = query.where(
        QueryPerformance.is_active & (QueryPerformance.consecutive_failures >= 3)
    ).count()
    
    total_executions = sum(qp.total_executions for qp in query)
    total_leads = sum(qp.total_leads_found for qp in query)
    total_qualified = sum(qp.total_qualified for qp in query)
    
    avg_success_rate = (total_leads / total_executions * 100) if total_executions > 0 else 0
    
    return {
        'total_queries': total_queries,
        'active_queries': active_queries,
        'stale_queries': stale_queries,
        'total_executions': total_executions,
        'total_leads_found': total_leads,
        'total_qualified': total_qualified,
        'average_success_rate': round(avg_success_rate, 2),
    }


def get_top_performing_queries(limit: int = 5, min_executions: int = 3) -> List[Dict]:
    """Get top performing queries by success rate (minimum executions required)"""
    query = (QueryPerformance
             .select(QueryPerformance, Bucket)
             .join(Bucket, on=(QueryPerformance.bucket_id == Bucket.id))
             .where(QueryPerformance.total_executions >= min_executions)
             .order_by((QueryPerformance.total_leads_found / QueryPerformance.total_executions).desc())
             .limit(limit))
    
    results = []
    for qp in query:
        success_rate = (qp.total_leads_found / qp.total_executions * 100) if qp.total_executions > 0 else 0
        results.append({
            'bucket': qp.bucket.name if qp.bucket else 'Unknown',
            'query_pattern': qp.query_pattern,
            'city': qp.city,
            'total_executions': qp.total_executions,
            'total_leads_found': qp.total_leads_found,
            'success_rate': round(success_rate, 2),
        })
    return results


def get_worst_performing_queries(limit: int = 5, min_executions: int = 3) -> List[Dict]:
    """Get worst performing queries by success rate (minimum executions required)"""
    query = (QueryPerformance
             .select(QueryPerformance, Bucket)
             .join(Bucket, on=(QueryPerformance.bucket_id == Bucket.id))
             .where(QueryPerformance.total_executions >= min_executions)
             .order_by((QueryPerformance.total_leads_found / QueryPerformance.total_executions).asc())
             .limit(limit))
    
    results = []
    for qp in query:
        success_rate = (qp.total_leads_found / qp.total_executions * 100) if qp.total_executions > 0 else 0
        results.append({
            'bucket': qp.bucket.name if qp.bucket else 'Unknown',
            'query_pattern': qp.query_pattern,
            'city': qp.city,
            'total_executions': qp.total_executions,
            'total_leads_found': qp.total_leads_found,
            'success_rate': round(success_rate, 2),
        })
    return results


def get_overall_efficiency_metrics() -> Dict:
    """Get overall efficiency metrics for query performance"""
    query = QueryPerformance.select()
    
    total_executions = sum(qp.total_executions for qp in query)
    total_leads_found = sum(qp.total_leads_found for qp in query)
    total_leads_saved = sum(qp.total_leads_saved for qp in query)
    total_qualified = sum(qp.total_qualified for qp in query)
    
    leads_per_execution = (total_leads_found / total_executions) if total_executions > 0 else 0
    save_rate = (total_leads_saved / total_leads_found * 100) if total_leads_found > 0 else 0
    qualification_rate = (total_qualified / total_leads_found * 100) if total_leads_found > 0 else 0
    
    return {
        'total_executions': total_executions,
        'total_leads_found': total_leads_found,
        'total_leads_saved': total_leads_saved,
        'total_qualified': total_qualified,
        'leads_per_execution': round(leads_per_execution, 2),
        'save_rate': round(save_rate, 2),
        'qualification_rate': round(qualification_rate, 2),
    }
