"""Database Repository Layer for Web Contractor.

All database operations - clean data access layer.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from peewee import DatabaseError, IntegrityError, JOIN

from core.db_models import (
    Bucket,
    EmailCampaign,
    Lead,
    QueryPerformance,
    db,
)


def init_db() -> None:
    """Initialize database and create tables."""
    db.connect(reuse_if_open=True)
    db.create_tables([Bucket, Lead, EmailCampaign, QueryPerformance], safe=True)


def close_db() -> None:
    """Close database connection."""
    if not db.is_closed():
        db.close()


def save_bucket(data: Dict[str, Any]) -> Bucket:
    """Save or update bucket.

    Args:
        data: Bucket data dictionary.

    Returns:
        Saved Bucket instance.
    """
    bucket_data = data.copy()

    bucket, created = Bucket.get_or_create(
        name=bucket_data["name"], defaults=bucket_data
    )

    if not created:
        for key, value in bucket_data.items():
            if key != "name" and hasattr(bucket, key):
                setattr(bucket, key, value)
        bucket.save()

    return bucket


def get_all_buckets() -> List[Dict[str, Any]]:
    """Get all buckets as dictionaries.

    Returns:
        List of bucket dictionaries.
    """
    return [bucket.to_dict() for bucket in Bucket.select()]


def get_bucket_id_by_name(name: str) -> Optional[int]:
    """Get bucket ID by name.

    Args:
        name: Bucket name.

    Returns:
        Bucket ID or None if not found.
    """
    bucket = Bucket.get_or_none(Bucket.name == name)
    return bucket.id if bucket else None


def save_lead(data: Dict[str, Any]) -> int:
    """Save single lead.

    Args:
        data: Lead data dictionary.

    Returns:
        Lead ID or -1 on error.
    """
    try:
        bucket_id = get_bucket_id_by_name(data.get("bucket", ""))

        lead = Lead.create(
            business_name=data.get("business_name"),
            category=data.get("category"),
            location=data.get("location"),
            phone=data.get("phone"),
            email=data.get("email"),
            website=data.get("website"),
            source=data.get("source"),
            bucket_id=bucket_id,
            quality_score=data.get("quality_score", 0.5),
            social_links=data.get("social_links", {}),
            contact_form_url=data.get("contact_form_url"),
            tech_stack=data.get("tech_stack"),
            metadata=data.get("metadata", {}),
        )
        return lead.id
    except (IntegrityError, DatabaseError) as e:
        print(f"Error saving lead: {e}")
        return -1


def save_leads_batch(leads: List[Dict[str, Any]]) -> int:
    """Save multiple leads in batch.

    Args:
        leads: List of lead data dictionaries.

    Returns:
        Number of leads saved.
    """
    if not leads:
        return 0

    bucket_map: Dict[str, Optional[int]] = {}
    bucket_names = {lead.get("bucket") for lead in leads if lead.get("bucket")}

    for bucket in Bucket.select().where(Bucket.name.in_(bucket_names)):
        bucket_map[bucket.name] = bucket.id

    insert_data = []
    for lead_data in leads:
        insert_data.append(
            {
                "business_name": lead_data.get("business_name"),
                "category": lead_data.get("category"),
                "location": lead_data.get("location"),
                "phone": lead_data.get("phone"),
                "email": lead_data.get("email"),
                "website": lead_data.get("website"),
                "source": lead_data.get("source"),
                "bucket_id": bucket_map.get(lead_data.get("bucket")),
                "quality_score": lead_data.get("quality_score", 0.5),
                "social_links": lead_data.get("social_links", {}),
                "contact_form_url": lead_data.get("contact_form_url"),
                "tech_stack": lead_data.get("tech_stack"),
                "metadata": lead_data.get("metadata", {}),
            }
        )

    try:
        with db.atomic():
            Lead.insert_many(insert_data).execute()
        return len(insert_data)
    except (IntegrityError, DatabaseError) as e:
        print(f"Error saving leads batch: {e}")
        return 0


def update_lead_contact_info(lead_id: int, info: Dict[str, Any]) -> None:
    """Update lead contact info.

    Args:
        lead_id: Lead ID.
        info: Contact info dictionary with email, phone, social_links, etc.
    """
    update_data: Dict[str, Any] = {}

    if "email" in info and info["email"]:
        update_data["email"] = info["email"]

    if "phone" in info and info["phone"]:
        update_data["phone"] = info["phone"]

    if "social_links" in info:
        update_data["social_links"] = info["social_links"]

    if "contact_form_url" in info:
        update_data["contact_form_url"] = info["contact_form_url"]

    if "tech_stack" in info:
        update_data["tech_stack"] = info["tech_stack"]

    if "metadata" in info:
        update_data["metadata"] = info["metadata"]

    if update_data:
        Lead.update(**update_data).where(Lead.id == lead_id).execute()


def get_pending_audits(limit: int = 50) -> List[Dict[str, Any]]:
    """Get leads pending audit.

    Args:
        limit: Maximum number of leads to return.

    Returns:
        List of lead dictionaries.
    """
    query = (
        Lead.select(Lead, Bucket)
        .join(Bucket, on=(Lead.bucket_id == Bucket.id), join_type=JOIN.LEFT_OUTER)
        .where((Lead.status == "pending_audit") & (Lead.website.is_null(False)))
        .limit(limit)
    )

    return [
        {
            "id": lead.id,
            "business_name": lead.business_name,
            "website": lead.website,
            "bucket": lead.bucket.name if lead.bucket else None,
        }
        for lead in query
    ]


def get_qualified_leads(limit: int = 50) -> List[Dict[str, Any]]:
    """Get qualified leads without emails.

    Args:
        limit: Maximum number of leads to return.

    Returns:
        List of lead dictionaries with audit info.
    """
    already_sent = EmailCampaign.select(EmailCampaign.lead_id)

    query = (
        Lead.select(Lead, Bucket)
        .join(Bucket, on=(Lead.bucket_id == Bucket.id), join_type=JOIN.LEFT_OUTER)
        .where((Lead.status == "qualified") & (Lead.id.not_in(already_sent)))
        .limit(limit)
    )

    result: List[Dict[str, Any]] = []
    for lead in query:
        result.append(
            {
                "id": lead.id,
                "business_name": lead.business_name,
                "website": lead.website,
                "bucket": lead.bucket.name if lead.bucket else None,
                "issues_json": lead.issues_json or [],
                "audit_score": lead.audit_score or 0,
            }
        )
    return result


def save_audits_batch(audits: List[Dict[str, Any]]) -> int:
    """Save audit results to Lead table.

    Args:
        audits: List of audit data dictionaries.

    Returns:
        Number of audits saved.
    """
    if not audits:
        return 0

    saved = 0
    with db.atomic():
        for audit_data in audits:
            try:
                lead_id = audit_data["lead_id"]
                data = audit_data.get("data", {})
                score = data.get("score", 0)
                issues = data.get("issues", [])
                qualified = bool(data.get("qualified", 0))

                Lead.update(
                    status="qualified" if qualified else "unqualified",
                    audit_score=score,
                    issues_json=issues,
                ).where(Lead.id == lead_id).execute()

                saved += 1
            except Exception as e:
                print(f"Error saving audit: {e}")
                continue

    return saved


def save_emails_batch(emails: List[Dict[str, Any]]) -> int:
    """Save multiple email campaigns.

    Args:
        emails: List of email campaign data dictionaries.

    Returns:
        Number of emails saved.
    """
    if not emails:
        return 0

    saved = 0
    with db.atomic():
        for email in emails:
            try:
                EmailCampaign.create(
                    lead_id=email.get("lead_id"),
                    subject=email.get("subject"),
                    body=email.get("body"),
                    status=email.get("status", "needs_review"),
                    duration=email.get("duration"),
                )
                saved += 1
            except Exception as e:
                print(f"Error saving email: {e}")
                continue

    return saved


def get_emails_for_review(limit: int = 50) -> List[Dict[str, Any]]:
    """Get emails needing review.

    Args:
        limit: Maximum number of emails to return.

    Returns:
        List of email campaign dictionaries.
    """
    query = (
        EmailCampaign.select(EmailCampaign, Lead)
        .join(Lead, on=(EmailCampaign.lead_id == Lead.id))
        .where(EmailCampaign.status == "needs_review")
        .limit(limit)
    )

    return [
        {
            "id": ec.id,
            "business_name": ec.lead.business_name,
            "email": ec.lead.email,
            "subject": ec.subject,
            "body": ec.body,
            "lead_id": ec.lead_id,
            "social_links": ec.lead.social_links or {},
            "contact_form_url": ec.lead.contact_form_url,
        }
        for ec in query
    ]


def update_email_content(campaign_id: int, subject: str, body: str) -> None:
    """Update email content.

    Args:
        campaign_id: Email campaign ID.
        subject: New subject line.
        body: New email body.
    """
    EmailCampaign.update(
        subject=subject,
        body=body,
        status="pending",
    ).where(EmailCampaign.id == campaign_id).execute()


def delete_email(campaign_id: int) -> None:
    """Delete email campaign.

    Args:
        campaign_id: Email campaign ID.
    """
    EmailCampaign.delete().where(EmailCampaign.id == campaign_id).execute()


def mark_email_sent(
    campaign_id: int, success: bool, error: Optional[str] = None
) -> None:
    """Mark email as sent.

    Args:
        campaign_id: Email campaign ID.
        success: Whether email was sent successfully.
        error: Error message if sending failed.
    """
    with db.atomic():
        if success:
            now = datetime.now()
            EmailCampaign.update(
                status="sent",
                sent_at=now,
                bounce_reason=None,
            ).where(EmailCampaign.id == campaign_id).execute()

            campaign = EmailCampaign.get_by_id(campaign_id)
            lead = Lead.get_by_id(campaign.lead_id)

            if lead.bucket_id:
                Bucket.update(daily_email_count=Bucket.daily_email_count + 1).where(
                    Bucket.id == lead.bucket_id
                ).execute()
        else:
            EmailCampaign.update(
                status="failed",
                bounce_reason=error,
                retry_count=EmailCampaign.retry_count + 1,
            ).where(
                (EmailCampaign.id == campaign_id)
                & (EmailCampaign.retry_count < EmailCampaign.max_retries)
            ).execute()

            EmailCampaign.update(status="permanently_failed").where(
                (EmailCampaign.id == campaign_id)
                & (EmailCampaign.retry_count >= EmailCampaign.max_retries)
            ).execute()


def get_or_create_query_performance(
    bucket_id: int, query_pattern: str, city: str
) -> QueryPerformance:
    """Get or create query performance tracking record.

    Args:
        bucket_id: Bucket ID.
        query_pattern: Query pattern.
        city: City name.

    Returns:
        QueryPerformance instance.
    """
    try:
        qp, _ = QueryPerformance.get_or_create(
            bucket_id=bucket_id,
            query_pattern=query_pattern,
            city=city,
            defaults={"is_active": True},
        )
        return qp
    except Exception:
        return QueryPerformance.create(
            bucket_id=bucket_id,
            query_pattern=query_pattern,
            city=city,
            is_active=True,
        )


def update_query_performance(
    query_perf: QueryPerformance,
    leads_found: int,
    leads_saved: int,
    qualified_count: int = 0,
    success: bool = True,
) -> None:
    """Update query performance metrics after execution.

    Args:
        query_perf: QueryPerformance instance.
        leads_found: Number of leads found.
        leads_saved: Number of leads saved.
        qualified_count: Number of qualified leads.
        success: Whether query executed successfully.
    """
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
    """Mark a query as stale (inactive).

    Args:
        query_perf: QueryPerformance instance.
    """
    QueryPerformance.update(is_active=False).where(
        QueryPerformance.id == query_perf.id
    ).execute()


def get_stale_queries(
    max_failures: int = 3, bucket_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get queries that have exceeded the failure threshold.

    Args:
        max_failures: Maximum consecutive failures.
        bucket_id: Optional bucket ID filter.

    Returns:
        List of stale query dictionaries.
    """
    query = (
        QueryPerformance.select(QueryPerformance, Bucket)
        .join(
            Bucket,
            on=(QueryPerformance.bucket_id == Bucket.id),
            join_type=JOIN.LEFT_OUTER,
        )
        .where(
            QueryPerformance.is_active
            & (QueryPerformance.consecutive_failures >= max_failures)
        )
    )

    if bucket_id:
        query = query.where(QueryPerformance.bucket_id == bucket_id)

    return [qp.to_dict() for qp in query]


def cleanup_stale_queries(days_threshold: int = 30) -> int:
    """Clean up very old stale queries to free up database space.

    Removes queries that have been inactive for more than the specified days.
    This helps prevent the database from growing too large with old stale queries.

    Args:
        days_threshold: Number of days after which stale queries are cleaned up.

    Returns:
        Number of queries cleaned up.
    """
    from datetime import datetime, timedelta

    cutoff_date = datetime.now() - timedelta(days=days_threshold)

    stale_old = QueryPerformance.select().where(
        ~QueryPerformance.is_active,
        QueryPerformance.last_executed_at < cutoff_date,
    )

    # Use bulk delete for better performance
    count = stale_old.count()
    QueryPerformance.delete().where(
        ~QueryPerformance.is_active,
        QueryPerformance.last_executed_at < cutoff_date,
    ).execute()

    return count


def get_query_performance_stats(
    bucket_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get overall query performance statistics.

    Args:
        bucket_id: Optional bucket ID filter.

    Returns:
        Statistics dictionary.
    """
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

    avg_success_rate = (
        (total_leads / total_executions * 100) if total_executions > 0 else 0
    )

    return {
        "total_queries": total_queries,
        "active_queries": active_queries,
        "stale_queries": stale_queries,
        "total_executions": total_executions,
        "total_leads_found": total_leads,
        "total_qualified": total_qualified,
        "average_success_rate": round(avg_success_rate, 2),
    }


def get_top_performing_queries(
    limit: int = 5, min_executions: int = 3
) -> List[Dict[str, Any]]:
    """Get top performing queries by success rate.

    Args:
        limit: Maximum number of queries to return.
        min_executions: Minimum executions required.

    Returns:
        List of top performing query dictionaries.
    """
    query = (
        QueryPerformance.select(QueryPerformance, Bucket)
        .join(Bucket, on=(QueryPerformance.bucket_id == Bucket.id))
        .where(QueryPerformance.total_executions >= min_executions)
        .order_by(
            (
                QueryPerformance.total_leads_found / QueryPerformance.total_executions
            ).desc()
        )
        .limit(limit)
    )

    results: List[Dict[str, Any]] = []
    for qp in query:
        success_rate = (
            (qp.total_leads_found / qp.total_executions * 100)
            if qp.total_executions > 0
            else 0
        )
        results.append(
            {
                "bucket": qp.bucket.name if qp.bucket else "Unknown",
                "query_pattern": qp.query_pattern,
                "city": qp.city,
                "total_executions": qp.total_executions,
                "total_leads_found": qp.total_leads_found,
                "success_rate": round(success_rate, 2),
            }
        )
    return results


def get_worst_performing_queries(
    limit: int = 5, min_executions: int = 3
) -> List[Dict[str, Any]]:
    """Get worst performing queries by success rate.

    Args:
        limit: Maximum number of queries to return.
        min_executions: Minimum executions required.

    Returns:
        List of worst performing query dictionaries.
    """
    query = (
        QueryPerformance.select(QueryPerformance, Bucket)
        .join(Bucket, on=(QueryPerformance.bucket_id == Bucket.id))
        .where(QueryPerformance.total_executions >= min_executions)
        .order_by(
            (
                QueryPerformance.total_leads_found / QueryPerformance.total_executions
            ).asc()
        )
        .limit(limit)
    )

    results: List[Dict[str, Any]] = []
    for qp in query:
        success_rate = (
            (qp.total_leads_found / qp.total_executions * 100)
            if qp.total_executions > 0
            else 0
        )
        results.append(
            {
                "bucket": qp.bucket.name if qp.bucket else "Unknown",
                "query_pattern": qp.query_pattern,
                "city": qp.city,
                "total_executions": qp.total_executions,
                "total_leads_found": qp.total_leads_found,
                "success_rate": round(success_rate, 2),
            }
        )
    return results


def get_overall_efficiency_metrics() -> Dict[str, Any]:
    """Get overall efficiency metrics for query performance.

    Returns:
        Efficiency metrics dictionary.
    """
    query = QueryPerformance.select()

    total_executions = sum(qp.total_executions for qp in query)
    total_leads_found = sum(qp.total_leads_found for qp in query)
    total_leads_saved = sum(qp.total_leads_saved for qp in query)
    total_qualified = sum(qp.total_qualified for qp in query)

    leads_per_execution = (
        (total_leads_found / total_executions) if total_executions > 0 else 0
    )
    save_rate = (
        (total_leads_saved / total_leads_found * 100) if total_leads_found > 0 else 0
    )
    qualification_rate = (
        (total_qualified / total_leads_found * 100) if total_leads_found > 0 else 0
    )

    return {
        "total_executions": total_executions,
        "total_leads_found": total_leads_found,
        "total_leads_saved": total_leads_saved,
        "total_qualified": total_qualified,
        "leads_per_execution": round(leads_per_execution, 2),
        "save_rate": round(save_rate, 2),
        "qualification_rate": round(qualification_rate, 2),
    }
