"""Simplified Peewee ORM Models for Web Contractor

Uses Peewee's native functions for maximum simplicity.
No repository pattern - direct model access.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Generator

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



def init_db():
    """Initialize database and create tables"""
    db.connect(reuse_if_open=True)
    db.create_tables([Bucket, Lead, Audit, AuditIssue, EmailCampaign, AppConfig], safe=True)
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


def save_audit(lead_id: int, data: Dict, duration: Optional[float] = None) -> None:
    """Save audit results"""
    with db.atomic():
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


def stream_qualified_leads(batch_size: int = 100) -> Generator[Dict, None, None]:
    """Stream qualified leads"""
    already_sent = EmailCampaign.select(EmailCampaign.lead_id)
    query = (Lead
             .select(Lead, Bucket)
             .join(Bucket, on=(Lead.bucket_id == Bucket.id), join_type=JOIN.LEFT_OUTER)
             .where(
                 (Lead.status == 'qualified') &
                 (Lead.id.not_in(already_sent))
             ))
    
    leads_with_audits = prefetch(query, Audit)

    for lead in leads_with_audits:
        latest_audit = lead.audits[0] if lead.audits else None
        yield {
            'id': lead.id,
            'business_name': lead.business_name,
            'website': lead.website,
            'bucket': lead.bucket.name if lead.bucket else None,
            'issues_json': latest_audit.issues_json if latest_audit and latest_audit.issues_json else '[]',
        }


def save_email(lead_id: int, subject: str, body: str, status: str = 'needs_review', duration: Optional[float] = None) -> None:
    """Save generated email"""
    EmailCampaign.create(
        lead_id=lead_id,
        subject=subject,
        body=body,
        status=status,
        duration=duration,
    )


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


def get_pending_emails(limit: int = 20) -> List[Dict]:
    """Get pending emails to send"""
    over_limit_ids = [b.id for b in Bucket.select(Bucket.id).where(
        (Bucket.daily_email_count >= Bucket.daily_email_limit) &
        (Bucket.last_reset_date >= datetime.now().date())
    )]

    query = (EmailCampaign
             .select(EmailCampaign, Lead)
             .join(Lead, on=(EmailCampaign.lead_id == Lead.id))
             .where((EmailCampaign.status == 'pending') & (Lead.email.is_null(False))))

    if over_limit_ids:
        query = query.where(Lead.bucket_id.not_in(over_limit_ids))

    query = query.limit(limit)

    return [{
        'campaign_id': ec.id,
        'business_name': ec.lead.business_name,
        'email': ec.lead.email,
        'subject': ec.subject,
        'body': ec.body,
        'lead_id': ec.lead_id,
    } for ec in query]


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


def get_emails_needing_review(limit: int = 50) -> List[Dict]:
    """Alias for get_emails_for_review"""
    return get_emails_for_review(limit)


def update_email_status(campaign_id: int, status: str) -> None:
    """Update email status"""
    EmailCampaign.update(status=status).where(EmailCampaign.id == campaign_id).execute()


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
