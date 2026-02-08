"""Optimized Lead Repository for Web Contractor TUI

Performance optimizations:
- SQLite WAL mode for better concurrency
- Thread-local connection pooling
- Optimized batch methods
- Streaming query methods for large datasets
- Connection timeout and retry logic
"""

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional


class LeadRepository:
    """Centralized database operations with connection pooling and WAL mode"""

    def __init__(self, db_path: str = "leads.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_wal_mode()

    def _init_wal_mode(self) -> None:
        """Enable WAL mode for better concurrency"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("PRAGMA mmap_size = 268435456")  # 256MB memory mapping
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection with proper settings"""
        conn: Optional[sqlite3.Connection] = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
            )
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.connection = conn
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections with retry logic"""
        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                conn = self._get_connection()
                yield conn
                return
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay * (2**attempt))  # Exponential backoff
                    continue
                raise

    @contextmanager
    def transaction(self):
        """Context manager for database transactions"""
        with self.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def __enter__(self):
        """Context manager entry"""
        self._conn = self._get_connection()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if hasattr(self, "_conn"):
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()

    def log(self, message: str, style: str = "") -> None:
        """Log message with optional style"""
        print(f"[{style.upper()}] {message}")

    def setup_database(self) -> None:
        """Initialize improved database schema with all optimizations"""
        with self.transaction() as conn:
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT NOT NULL,
                category TEXT,
                location TEXT,
                phone TEXT,
                email TEXT,
                website TEXT UNIQUE,
                source TEXT,
                status TEXT DEFAULT 'pending_audit',
                quality_score REAL DEFAULT 0.5,
                bucket_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_email_sent_at TIMESTAMP,
                social_links TEXT,  -- JSON object
                contact_form_url TEXT,
                FOREIGN KEY(bucket_id) REFERENCES buckets(id) ON DELETE SET NULL
            )
            """)

            # Migrations for existing tables
            try:
                cursor.execute("ALTER TABLE leads ADD COLUMN social_links TEXT")
            except sqlite3.OperationalError:
                pass  # social_links column already exists

            try:
                cursor.execute("ALTER TABLE leads ADD COLUMN contact_form_url TEXT")
            except sqlite3.OperationalError:
                pass  # contact_form_url column already exists

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                url TEXT,
                score INTEGER,
                issues_json TEXT,
                qualified INTEGER DEFAULT 0,
                duration REAL,  -- Time taken in seconds
                audit_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                subject TEXT,
                body TEXT,
                status TEXT DEFAULT 'pending',
                duration REAL,  -- Time taken for generation
                sent_at TIMESTAMP,
                opened_at TIMESTAMP,
                clicked_at TIMESTAMP,
                replied_at TIMESTAMP,
                bounce_reason TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_at TIMESTAMP,
                max_retries INTEGER DEFAULT 3,
                FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS buckets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                categories TEXT,  -- JSON list
                search_patterns TEXT,  -- JSON list
                geographic_segments TEXT,  -- JSON list
                intent_profile TEXT,
                conversion_probability REAL,
                monthly_target INTEGER,
                daily_email_count INTEGER DEFAULT 0,
                last_reset_date DATE DEFAULT CURRENT_DATE,
                daily_email_limit INTEGER DEFAULT 500
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id INTEGER NOT NULL,
                issue_type TEXT NOT NULL,
                severity TEXT CHECK(severity IN ('critical', 'warning', 'info')),
                description TEXT,
                FOREIGN KEY(audit_id) REFERENCES audits(id) ON DELETE CASCADE
            )
            """)

            # App config table (keeping for system settings)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT -- JSON value
            )
            """)

            # Migrations for duration columns
            try:
                cursor.execute("ALTER TABLE audits ADD COLUMN duration REAL")
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute("ALTER TABLE email_campaigns ADD COLUMN duration REAL")
            except sqlite3.OperationalError:
                pass

            # Performance indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_bucket ON leads(bucket_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_audits_qualified ON audits(qualified)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_audits_lead_id ON audits(lead_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_campaigns_status ON email_campaigns(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_campaigns_lead_status ON email_campaigns(lead_id, status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_issues_audit_id ON audit_issues(audit_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_issues_type ON audit_issues(issue_type)"
            )

    def save_bucket(self, bucket_data: Dict) -> None:
        """Save or update a bucket configuration"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO buckets (name, categories, search_patterns, geographic_segments,
                                   intent_profile, conversion_probability, monthly_target,
                                   daily_email_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    categories=excluded.categories,
                    search_patterns=excluded.search_patterns,
                    geographic_segments=excluded.geographic_segments,
                    intent_profile=excluded.intent_profile,
                    conversion_probability=excluded.conversion_probability,
                    monthly_target=excluded.monthly_target,
                    daily_email_limit=excluded.daily_email_limit
            """,
                (
                    bucket_data["name"],
                    json.dumps(bucket_data.get("categories", [])),
                    json.dumps(bucket_data.get("search_patterns", [])),
                    json.dumps(bucket_data.get("geographic_segments", [])),
                    bucket_data.get("intent_profile", ""),
                    bucket_data.get("conversion_probability", 0.0),
                    bucket_data.get("monthly_target", 0),
                    bucket_data.get("daily_email_limit", 500),
                ),
            )

    def get_all_buckets(self) -> List[Dict]:
        """Get all configured buckets"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM buckets")
            columns = [description[0] for description in cursor.description]
            buckets = []

            for row in cursor.fetchall():
                d = dict(zip(columns, row))
                # Parse JSON fields
                for field in ["categories", "search_patterns", "geographic_segments"]:
                    if d.get(field):
                        try:
                            d[field] = json.loads(d[field])
                        except json.JSONDecodeError as e:
                            self.log(f"Invalid JSON in bucket.{field}: {e}", "error")
                            d[field] = []
                buckets.append(d)

        return buckets

    def get_bucket_id_by_name(self, bucket_name: str) -> Optional[int]:
        """Get bucket ID by name for foreign key relationship"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM buckets WHERE name = ?", (bucket_name,))
            result = cursor.fetchone()
            return result[0] if result else None

    def save_config(self, key: str, value: Dict) -> None:
        """Save global config"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO app_config (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
                (key, json.dumps(value)),
            )

    def get_config(self, key: str) -> Optional[Dict]:
        """Get global config"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_config WHERE key = ?", (key,))
            row = cursor.fetchone()

            if row:
                try:
                    result: Dict = json.loads(row[0])
                    return result
                except json.JSONDecodeError as e:
                    self.log(
                        f"Invalid JSON in config value for key '{key}': {e}", "error"
                    )
                    return None
                except Exception as e:
                    self.log(
                        f"Unexpected error loading config for key '{key}': {e}", "error"
                    )
                    return None
        return None

    def save_leads_batch(self, leads: List[Dict]) -> int:
        """Save multiple leads in a single transaction"""
        if not leads:
            return 0

        saved_count = 0
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Pre-fetch bucket IDs for all unique buckets
            bucket_names = {lead.get("bucket") for lead in leads if lead.get("bucket")}
            bucket_id_map = {}
            if bucket_names:
                placeholders = ",".join("?" * len(bucket_names))
                cursor.execute(
                    f"SELECT id, name FROM buckets WHERE name IN ({placeholders})",
                    tuple(bucket_names),
                )
                bucket_id_map = {name: id for id, name in cursor.fetchall()}

            for lead in leads:
                bucket_id = bucket_id_map.get(lead.get("bucket"))

                try:
                    cursor.execute(
                        """
                        INSERT INTO leads (business_name, category, location, phone, email,
                                           website, source, bucket_id, quality_score,
                                           social_links, contact_form_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            lead.get("business_name"),
                            lead.get("category"),
                            lead.get("location"),
                            lead.get("phone"),
                            lead.get("email"),
                            lead.get("website"),
                            lead.get("source"),
                            bucket_id,
                            lead.get("quality_score", 0.5),
                            json.dumps(lead.get("social_links", {})),
                            lead.get("contact_form_url"),
                        ),
                    )
                    saved_count += 1
                except sqlite3.IntegrityError:
                    continue
        return saved_count

    def save_lead(self, lead: Dict) -> int:
        """Save a single lead with bucket foreign key"""
        bucket_id = None
        if lead.get("bucket"):
            bucket_id = self.get_bucket_id_by_name(lead["bucket"])

        with self.transaction() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO leads (business_name, category, location, phone, email,
                                       website, source, bucket_id, quality_score,
                                       social_links, contact_form_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        lead.get("business_name"),
                        lead.get("category"),
                        lead.get("location"),
                        lead.get("phone"),
                        lead.get("email"),
                        lead.get("website"),
                        lead.get("source"),
                        bucket_id,
                        lead.get("quality_score", 0.5),
                        json.dumps(lead.get("social_links", {})),
                        lead.get("contact_form_url"),
                    ),
                )
                lead_id: int = cursor.lastrowid or -1
                return lead_id
            except sqlite3.IntegrityError:
                return -1

    def update_lead_contact_info(self, lead_id: int, contact_info: Dict) -> None:
        """Update lead contact information discovered during audit"""
        with self.transaction() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if "email" in contact_info and contact_info["email"]:
                updates.append("email = ?")
                params.append(contact_info["email"])

            if "phone" in contact_info and contact_info["phone"]:
                updates.append("phone = ?")
                params.append(contact_info["phone"])

            if "social_links" in contact_info:
                updates.append("social_links = ?")
                params.append(json.dumps(contact_info["social_links"]))

            if "contact_form_url" in contact_info:
                updates.append("contact_form_url = ?")
                params.append(contact_info["contact_form_url"])

            if updates:
                params.append(lead_id)
                query = f"UPDATE leads SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, params)

    def get_pending_audits(self, limit: int = 50) -> List[Dict]:
        """Get leads pending audit"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT l.id, l.business_name, l.website, b.name as bucket_name
                FROM leads l
                LEFT JOIN buckets b ON l.bucket_id = b.id
                WHERE l.status = 'pending_audit' AND l.website IS NOT NULL
                LIMIT ?
            """,
                (limit,),
            )

            leads = []
            for row in cursor.fetchall():
                leads.append(
                    {
                        "id": row[0],
                        "business_name": row[1],
                        "website": row[2],
                        "bucket": row[3],
                    }
                )

        return leads

    def save_audit(
        self, lead_id: int, audit_data: Dict, duration: Optional[float] = None
    ) -> None:
        """Save audit results with normalized issues and duration"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audits (lead_id, url, score, issues_json, qualified, duration)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    lead_id,
                    audit_data.get("url"),
                    audit_data.get("score", 0),
                    json.dumps(audit_data.get("issues", [])),
                    audit_data.get("qualified", 0),
                    duration,
                ),
            )

            audit_id = cursor.lastrowid

            # Save normalized issues
            for issue in audit_data.get("issues", []):
                cursor.execute(
                    """
                    INSERT INTO audit_issues (audit_id, issue_type, severity, description)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        audit_id,
                        issue.get("type", "unknown"),
                        issue.get("severity", "info"),
                        issue.get("description", ""),
                    ),
                )

            # Update lead status
            new_status = "qualified" if audit_data.get("qualified") else "unqualified"
            cursor.execute(
                """
                UPDATE leads SET status = ? WHERE id = ?
            """,
                (new_status, lead_id),
            )

    def save_audits_batch(self, audits: List[Dict]) -> int:
        """Save multiple audit results in a single transaction"""
        if not audits:
            return 0

        saved_count = 0
        with self.transaction() as conn:
            cursor = conn.cursor()

            for audit in audits:
                lead_id = audit.get("lead_id")
                audit_data = audit.get("data", {})
                duration = audit.get("duration")

                try:
                    cursor.execute(
                        """
                        INSERT INTO audits (lead_id, url, score, issues_json, qualified, duration)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            lead_id,
                            audit_data.get("url"),
                            audit_data.get("score", 0),
                            json.dumps(audit_data.get("issues", [])),
                            audit_data.get("qualified", 0),
                            duration,
                        ),
                    )

                    audit_id = cursor.lastrowid

                    # Save normalized issues
                    for issue in audit_data.get("issues", []):
                        cursor.execute(
                            """
                            INSERT INTO audit_issues (audit_id, issue_type, severity, description)
                            VALUES (?, ?, ?, ?)
                        """,
                            (
                                audit_id,
                                issue.get("type", "unknown"),
                                issue.get("severity", "info"),
                                issue.get("description", ""),
                            ),
                        )

                    # Update lead status
                    new_status = (
                        "qualified" if audit_data.get("qualified") else "unqualified"
                    )
                    cursor.execute(
                        "UPDATE leads SET status = ? WHERE id = ?",
                        (new_status, lead_id),
                    )

                    saved_count += 1
                except sqlite3.Error:
                    continue

        return saved_count

    def get_qualified_leads(self, limit: int = 50) -> List[Dict]:
        """Get qualified leads without emails - optimized query"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT l.id, l.business_name, l.website, b.name as bucket_name, a.issues_json
                FROM leads l
                JOIN audits a ON l.id = a.lead_id
                LEFT JOIN email_campaigns ec ON l.id = ec.lead_id
                LEFT JOIN buckets b ON l.bucket_id = b.id
                WHERE l.status = 'qualified'
                AND ec.id IS NULL
                LIMIT ?
            """,
                (limit,),
            )

            leads = []
            for row in cursor.fetchall():
                try:
                    leads.append(
                        {
                            "id": row[0],
                            "business_name": row[1],
                            "website": row[2],
                            "bucket": row[3],
                            "issues_json": row[4],
                        }
                    )
                except (IndexError, TypeError):
                    continue

        return leads

    def stream_qualified_leads(
        self, batch_size: int = 100
    ) -> Generator[Dict, None, None]:
        """Stream qualified leads for memory-efficient processing"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT l.id, l.business_name, l.website, b.name as bucket_name, a.issues_json
                FROM leads l
                JOIN audits a ON l.id = a.lead_id
                LEFT JOIN email_campaigns ec ON l.id = ec.lead_id
                LEFT JOIN buckets b ON l.bucket_id = b.id
                WHERE l.status = 'qualified'
                AND ec.id IS NULL
            """
            )

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break

                for row in rows:
                    try:
                        yield {
                            "id": row[0],
                            "business_name": row[1],
                            "website": row[2],
                            "bucket": row[3],
                            "issues_json": row[4],
                        }
                    except (IndexError, TypeError):
                        continue

    def save_email(
        self,
        lead_id: int,
        subject: str,
        body: str,
        status: str = "needs_review",
        duration: Optional[float] = None,
    ) -> None:
        """Save generated email with generation duration"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO email_campaigns (lead_id, subject, body, status, duration)
                VALUES (?, ?, ?, ?, ?)
            """,
                (lead_id, subject, body, status, duration),
            )

    def save_emails_batch(self, emails: List[Dict]) -> int:
        """Save multiple emails in a single transaction"""
        if not emails:
            return 0

        saved_count = 0
        with self.transaction() as conn:
            cursor = conn.cursor()

            for email in emails:
                try:
                    cursor.execute(
                        """
                        INSERT INTO email_campaigns (lead_id, subject, body, status, duration)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (
                            email.get("lead_id"),
                            email.get("subject"),
                            email.get("body"),
                            email.get("status", "needs_review"),
                            email.get("duration"),
                        ),
                    )
                    saved_count += 1
                except sqlite3.Error:
                    continue

        return saved_count

    def get_pending_emails(self, limit: int = 20) -> List[Dict]:
        """Get pending (approved) emails to send with rate limiting"""
        with self.connection() as conn:
            cursor = conn.cursor()

            # Check daily email limits
            cursor.execute("""
                SELECT id
                FROM buckets
                WHERE daily_email_count >= daily_email_limit
                AND last_reset_date = CURRENT_DATE
            """)
            over_limit_buckets = [row[0] for row in cursor.fetchall()]

            # Get pending emails, excluding leads in buckets over limit
            if over_limit_buckets:
                placeholders = ",".join("?" * len(over_limit_buckets))
                cursor.execute(
                    f"""
                    SELECT ec.id, l.business_name, l.email, ec.subject, ec.body, l.id as lead_id
                    FROM email_campaigns ec
                    JOIN leads l ON ec.lead_id = l.id
                    WHERE ec.status = 'pending'
                    AND l.email IS NOT NULL
                    AND (l.bucket_id IS NULL OR l.bucket_id NOT IN ({placeholders}))
                    LIMIT ?
                """,
                    over_limit_buckets + [limit],
                )
            else:
                cursor.execute(
                    """
                    SELECT ec.id, l.business_name, l.email, ec.subject, ec.body, l.id as lead_id
                    FROM email_campaigns ec
                    JOIN leads l ON ec.lead_id = l.id
                    WHERE ec.status = 'pending' AND l.email IS NOT NULL
                    LIMIT ?
                """,
                    (limit,),
                )

            emails = []
            for row in cursor.fetchall():
                emails.append(
                    {
                        "campaign_id": row[0],
                        "business_name": row[1],
                        "email": row[2],
                        "subject": row[3],
                        "body": row[4],
                        "lead_id": row[5],
                    }
                )

        return emails

    def get_emails_needing_review(self, limit: int = 50) -> List[Dict]:
        """Get emails with needs_review status"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ec.id, l.business_name, l.email, ec.subject, ec.body, l.id as lead_id,
                       l.social_links, l.contact_form_url
                FROM email_campaigns ec
                JOIN leads l ON ec.lead_id = l.id
                WHERE ec.status = 'needs_review'
                LIMIT ?
            """,
                (limit,),
            )

            emails = []
            for row in cursor.fetchall():
                emails.append(
                    {
                        "id": row[0],
                        "business_name": row[1],
                        "email": row[2],
                        "subject": row[3],
                        "body": row[4],
                        "lead_id": row[5],
                        "social_links": json.loads(row[6]) if row[6] else {},
                        "contact_form_url": row[7],
                    }
                )
        return emails

    def update_email_status(self, campaign_id: int, status: str) -> None:
        """Update email campaign status"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE email_campaigns SET status = ? WHERE id = ?",
                (status, campaign_id),
            )

    def update_email_content(self, campaign_id: int, subject: str, body: str) -> None:
        """Update email campaign content"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE email_campaigns
                SET subject = ?, body = ?, status = 'pending'
                WHERE id = ?
            """,
                (subject, body, campaign_id),
            )

    def delete_email(self, campaign_id: int) -> None:
        """Delete an email campaign"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM email_campaigns WHERE id = ?", (campaign_id,))

    def mark_email_sent(
        self, campaign_id: int, success: bool, error: Optional[str] = None
    ) -> None:
        """Mark email as sent or failed with retry logic"""
        with self.transaction() as conn:
            cursor = conn.cursor()

            if success:
                from datetime import datetime

                now = datetime.now().isoformat()
                cursor.execute(
                    """
                    UPDATE email_campaigns
                    SET status = 'sent', sent_at = ?, bounce_reason = NULL
                    WHERE id = ?
                """,
                    (now, campaign_id),
                )

                # Update last_email_sent_at for the lead
                cursor.execute(
                    """
                    UPDATE leads SET last_email_sent_at = ?
                    WHERE id = (SELECT lead_id FROM email_campaigns WHERE id = ?)
                """,
                    (now, campaign_id),
                )

                # Update bucket daily email count
                cursor.execute(
                    """
                    UPDATE buckets
                    SET daily_email_count = daily_email_count + 1
                    WHERE id = (
                        SELECT l.bucket_id FROM leads l
                        JOIN email_campaigns ec ON l.id = ec.lead_id
                        WHERE ec.id = ?
                    )
                """,
                    (campaign_id,),
                )
            else:
                # Handle failed email with retry logic
                cursor.execute(
                    """
                    UPDATE email_campaigns
                    SET status = 'failed', bounce_reason = ?,
                        retry_count = retry_count + 1,
                        next_retry_at = datetime('now', '+' || (retry_count + 1) * 3600 || ' seconds')
                    WHERE id = ? AND retry_count < max_retries
                """,
                    (error, campaign_id),
                )

                # Mark as permanently failed if max retries reached
                cursor.execute(
                    """
                    UPDATE email_campaigns
                    SET status = 'permanently_failed'
                    WHERE id = ? AND retry_count >= max_retries
                """,
                    (campaign_id,),
                )

    def close(self) -> None:
        """Close thread-local connection if exists"""
        if hasattr(self._local, "connection") and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None
