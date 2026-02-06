"""Simplified Lead Repository for Web Contractor TUI"""
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime


class LeadRepository:
    """Centralized database operations"""

    def __init__(self, db_path="leads.db"):
        self.db_path = db_path

    def _get_connection(self):
        """Get database connection with proper settings"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def __enter__(self):
        """Context manager entry"""
        self._conn = self._get_connection()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if hasattr(self, '_conn'):
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
            self._conn.close()

    def setup_database(self):
        """Initialize improved database schema with all optimizations"""
        with self._get_connection() as conn:
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
                FOREIGN KEY(bucket_id) REFERENCES buckets(id) ON DELETE SET NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                url TEXT,
                score INTEGER,
                issues_json TEXT,
                qualified INTEGER DEFAULT 0,
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

                # Simplified email_templates table (keeping for backward compatibility)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bucket_id INTEGER,
                issue_type TEXT,
                template_id TEXT,
                subject_pattern TEXT,
                body_template TEXT,
                tone TEXT,
                word_count_range TEXT, -- JSON list
                conversion_focus TEXT,
                FOREIGN KEY(bucket_id) REFERENCES buckets(id) ON DELETE CASCADE,
                UNIQUE(bucket_id, issue_type)
            )
            """)

            # App config table (keeping for system settings)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT -- JSON value
            )
            """)

            # Performance indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_bucket ON leads(bucket_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_qualified ON audits(qualified)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_lead_id ON audits(lead_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_campaigns_status ON email_campaigns(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_campaigns_lead_status ON email_campaigns(lead_id, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_issues_audit_id ON audit_issues(audit_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_issues_type ON audit_issues(issue_type)")

    def save_bucket(self, bucket_data: Dict):
        """Save or update a bucket configuration"""
        import json
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
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
            """, (
                bucket_data["name"],
                json.dumps(bucket_data.get("categories", [])),
                json.dumps(bucket_data.get("search_patterns", [])),
                json.dumps(bucket_data.get("geographic_segments", [])),
                bucket_data.get("intent_profile", ""),
                bucket_data.get("conversion_probability", 0.0),
                bucket_data.get("monthly_target", 0),
                bucket_data.get("daily_email_limit", 500)
            ))

    def get_all_buckets(self) -> List[Dict]:
        """Get all configured buckets"""
        import json
        
        with self._get_connection() as conn:
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
                        except:
                            d[field] = []
                buckets.append(d)
            
        return buckets

    def get_bucket_id_by_name(self, bucket_name: str) -> Optional[int]:
        """Get bucket ID by name for foreign key relationship"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM buckets WHERE name = ?", (bucket_name,))
            result = cursor.fetchone()
            return result[0] if result else None

    def save_template(self, bucket_name: str, issue_type: str, template_data: Dict):
        """Save email template with bucket foreign key"""
        import json
        
        bucket_id = self.get_bucket_id_by_name(bucket_name)
        if not bucket_id:
            raise ValueError(f"Bucket '{bucket_name}' not found")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO email_templates (bucket_id, issue_type, template_id, subject_pattern, 
                                           body_template, tone, word_count_range, conversion_focus)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket_id, issue_type) DO UPDATE SET
                    template_id=excluded.template_id,
                    subject_pattern=excluded.subject_pattern,
                    body_template=excluded.body_template,
                    tone=excluded.tone,
                    word_count_range=excluded.word_count_range,
                    conversion_focus=excluded.conversion_focus
            """, (
                bucket_id,
                issue_type,
                template_data.get("template_id"),
                template_data.get("subject_pattern"),
                template_data.get("body_template"),
                template_data.get("tone"),
                json.dumps(template_data.get("word_count_range", [])),
                template_data.get("conversion_focus")
            ))

    def get_templates_for_bucket(self, bucket_name: str) -> Dict:
        """Get all templates for a bucket"""
        import json
        
        bucket_id = self.get_bucket_id_by_name(bucket_name)
        if not bucket_id:
            return {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM email_templates WHERE bucket_id = ?", (bucket_id,))
            columns = [description[0] for description in cursor.description]
            
            templates = {}
            for row in cursor.fetchall():
                d = dict(zip(columns, row))
                issue_type = d.pop("issue_type")
                if d.get("word_count_range"):
                    try:
                        d["word_count_range"] = json.loads(d["word_count_range"])
                    except:
                        d["word_count_range"] = []
                templates[issue_type] = d
            
        return templates

    def save_config(self, key: str, value: Dict):
        """Save global config"""
        import json
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_config (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (key, json.dumps(value)))

    def get_config(self, key: str) -> Optional[Dict]:
        """Get global config"""
        import json
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_config WHERE key = ?", (key,))
            row = cursor.fetchone()
            
        if row:
            try:
                return json.loads(row[0])
            except:
                return None
        return None

    def save_lead(self, lead: Dict) -> int:
        """Save a single lead with bucket foreign key"""
        bucket_id = None
        if lead.get("bucket"):
            bucket_id = self.get_bucket_id_by_name(lead["bucket"])
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO leads (business_name, category, location, phone, email, 
                                       website, source, bucket_id, quality_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lead.get("business_name"),
                    lead.get("category"),
                    lead.get("location"),
                    lead.get("phone"),
                    lead.get("email"),
                    lead.get("website"),
                    lead.get("source"),
                    bucket_id,
                    lead.get("quality_score", 0.5)
                ))
                lead_id = cursor.lastrowid
                return lead_id
            except sqlite3.IntegrityError:
                return -1

    def get_pending_audits(self, limit: int = 50) -> List[Dict]:
        """Get leads pending audit"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.id, l.business_name, l.website, b.name as bucket_name
                FROM leads l
                LEFT JOIN buckets b ON l.bucket_id = b.id
                WHERE l.status = 'pending_audit' AND l.website IS NOT NULL
                LIMIT ?
            """, (limit,))
            
            leads = []
            for row in cursor.fetchall():
                leads.append({
                    "id": row[0],
                    "business_name": row[1],
                    "website": row[2],
                    "bucket": row[3]
                })
        
        return leads

    def save_audit(self, lead_id: int, audit_data: Dict):
        """Save audit results with normalized issues"""
        import json
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audits (lead_id, url, score, issues_json, qualified)
                VALUES (?, ?, ?, ?, ?)
            """, (
                lead_id,
                audit_data.get("url"),
                audit_data.get("score", 0),
                json.dumps(audit_data.get("issues", [])),
                audit_data.get("qualified", 0)
            ))
            
            audit_id = cursor.lastrowid
            
            # Save normalized issues
            for issue in audit_data.get("issues", []):
                cursor.execute("""
                    INSERT INTO audit_issues (audit_id, issue_type, severity, description)
                    VALUES (?, ?, ?, ?)
                """, (
                    audit_id,
                    issue.get("type", "unknown"),
                    issue.get("severity", "info"),
                    issue.get("description", "")
                ))
            
            # Update lead status
            new_status = "qualified" if audit_data.get("qualified") else "unqualified"
            cursor.execute("""
                UPDATE leads SET status = ? WHERE id = ?
            """, (new_status, lead_id))

    def get_qualified_leads(self, limit: int = 50) -> List[Dict]:
        """Get qualified leads without emails - optimized query"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.id, l.business_name, l.website, b.name as bucket_name, a.issues_json
                FROM leads l
                JOIN audits a ON l.id = a.lead_id
                LEFT JOIN email_campaigns ec ON l.id = ec.lead_id
                LEFT JOIN buckets b ON l.bucket_id = b.id
                WHERE l.status = 'qualified' 
                AND ec.id IS NULL
                LIMIT ?
            """, (limit,))
            
            leads = []
            for row in cursor.fetchall():
                leads.append({
                    "id": row[0],
                    "business_name": row[1],
                    "website": row[2],
                    "bucket": row[3],
                    "issues_json": row[4]
                })
        
        return leads

    def save_email(self, lead_id: int, subject: str, body: str):
        """Save generated email"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO email_campaigns (lead_id, subject, body)
                VALUES (?, ?, ?)
            """, (lead_id, subject, body))
            
            # Update last_email_sent_at for the lead
            cursor.execute("""
                UPDATE leads SET last_email_sent_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (lead_id,))

    def get_pending_emails(self, limit: int = 20) -> List[Dict]:
        """Get pending emails to send with rate limiting"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check daily email limits
            cursor.execute("""
                SELECT daily_email_count, daily_email_limit, last_reset_date 
                FROM buckets 
                WHERE daily_email_count >= daily_email_limit 
                AND last_reset_date = CURRENT_DATE
            """)
            over_limit_buckets = [row[0] for row in cursor.fetchall()]
            
            # Get pending emails, excluding leads in buckets over limit
            if over_limit_buckets:
                placeholders = ','.join('?' * len(over_limit_buckets))
                cursor.execute(f"""
                    SELECT ec.id, l.business_name, l.email, ec.subject, ec.body, l.id as lead_id
                    FROM email_campaigns ec
                    JOIN leads l ON ec.lead_id = l.id
                    WHERE ec.status = 'pending' 
                    AND l.email IS NOT NULL
                    AND (l.bucket_id IS NULL OR l.bucket_id NOT IN ({placeholders}))
                    LIMIT ?
                """, over_limit_buckets + [limit])
            else:
                cursor.execute("""
                    SELECT ec.id, l.business_name, l.email, ec.subject, ec.body, l.id as lead_id
                    FROM email_campaigns ec
                    JOIN leads l ON ec.lead_id = l.id
                    WHERE ec.status = 'pending' AND l.email IS NOT NULL
                    LIMIT ?
                """, (limit,))
            
            emails = []
            for row in cursor.fetchall():
                emails.append({
                    "campaign_id": row[0],
                    "business_name": row[1],
                    "email": row[2],
                    "subject": row[3],
                    "body": row[4],
                    "lead_id": row[5]
                })
        
        return emails

    def mark_email_sent(self, campaign_id: int, success: bool, error: str = None):
        """Mark email as sent or failed with retry logic"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if success:
                cursor.execute("""
                    UPDATE email_campaigns 
                    SET status = 'sent', sent_at = ?, bounce_reason = NULL
                    WHERE id = ?
                """, (datetime.now().isoformat(), campaign_id))
                
                # Update bucket daily email count
                cursor.execute("""
                    UPDATE buckets 
                    SET daily_email_count = daily_email_count + 1
                    WHERE id = (
                        SELECT l.bucket_id FROM leads l 
                        JOIN email_campaigns ec ON l.id = ec.lead_id 
                        WHERE ec.id = ?
                    )
                """, (campaign_id,))
            else:
                # Handle failed email with retry logic
                cursor.execute("""
                    UPDATE email_campaigns 
                    SET status = 'failed', bounce_reason = ?, 
                        retry_count = retry_count + 1,
                        next_retry_at = datetime('now', '+' || (retry_count + 1) * 3600 || ' seconds')
                    WHERE id = ? AND retry_count < max_retries
                """, (error, campaign_id))
                
                # Mark as permanently failed if max retries reached
                cursor.execute("""
                    UPDATE email_campaigns 
                    SET status = 'permanently_failed'
                    WHERE id = ? AND retry_count >= max_retries
                """, (campaign_id,))

    def get_stats(self) -> Dict:
        """Get overall statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM leads")
            total_leads = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'qualified'")
            qualified = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM email_campaigns WHERE status = 'sent'")
            emails_sent = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM email_campaigns WHERE status = 'pending'")
            emails_pending = cursor.fetchone()[0]
            
            # Email engagement stats
            cursor.execute("SELECT COUNT(*) FROM email_campaigns WHERE opened_at IS NOT NULL")
            emails_opened = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM email_campaigns WHERE clicked_at IS NOT NULL")
            emails_clicked = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM email_campaigns WHERE replied_at IS NOT NULL")
            emails_replied = cursor.fetchone()[0]
            
        return {
            "total_leads": total_leads,
            "qualified_leads": qualified,
            "emails_sent": emails_sent,
            "emails_pending": emails_pending,
            "emails_opened": emails_opened,
            "emails_clicked": emails_clicked,
            "emails_replied": emails_replied
        }

    def consolidate_database(self) -> Dict:
        """Clean up and optimize database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Remove leads with absolutely no contact info
            cursor.execute("""
                DELETE FROM leads 
                WHERE (website IS NULL OR website = '') 
                AND (phone IS NULL OR phone = '') 
                AND (email IS NULL OR email = '')
            """)
            deleted_count = cursor.rowcount
            
            # 2. Reset daily email counters for new day
            cursor.execute("""
                UPDATE buckets 
                SET daily_email_count = 0, last_reset_date = CURRENT_DATE
                WHERE last_reset_date < CURRENT_DATE
            """)
            reset_count = cursor.rowcount
            
            # 3. Retry failed emails that are ready
            cursor.execute("""
                UPDATE email_campaigns 
                SET status = 'pending'
                WHERE status = 'failed' 
                AND next_retry_at <= CURRENT_TIMESTAMP
                AND retry_count < max_retries
            """)
            retry_count = cursor.rowcount
            
            # 4. Optimize database
            cursor.execute("VACUUM")
            
        return {
            "deleted_empty_leads": deleted_count,
            "reset_daily_counters": reset_count,
            "emails_queued_for_retry": retry_count,
            "status": "optimized"
        }

    # New methods for email engagement tracking
    def track_email_opened(self, campaign_id: int):
        """Track when email is opened"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_campaigns 
                SET opened_at = CURRENT_TIMESTAMP 
                WHERE id = ? AND opened_at IS NULL
            """, (campaign_id,))

    def track_email_clicked(self, campaign_id: int):
        """Track when email link is clicked"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_campaigns 
                SET clicked_at = CURRENT_TIMESTAMP 
                WHERE id = ? AND clicked_at IS NULL
            """, (campaign_id,))

    def track_email_replied(self, campaign_id: int):
        """Track when prospect replies to email"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_campaigns 
                SET replied_at = CURRENT_TIMESTAMP 
                WHERE id = ? AND replied_at IS NULL
            """, (campaign_id,))

    def get_retry_emails(self, limit: int = 10) -> List[Dict]:
        """Get emails ready for retry"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ec.id, l.business_name, l.email, ec.subject, ec.body, l.id as lead_id
                FROM email_campaigns ec
                JOIN leads l ON ec.lead_id = l.id
                WHERE ec.status = 'failed' 
                AND ec.next_retry_at <= CURRENT_TIMESTAMP
                AND ec.retry_count < ec.max_retries
                LIMIT ?
            """, (limit,))
            
            emails = []
            for row in cursor.fetchall():
                emails.append({
                    "campaign_id": row[0],
                    "business_name": row[1],
                    "email": row[2],
                    "subject": row[3],
                    "body": row[4],
                    "lead_id": row[5]
                })
        
        return emails

    def get_issues_by_type(self, issue_type: str) -> List[Dict]:
        """Get all audits with specific issue type"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.id, l.business_name, l.website, ai.description, ai.severity
                FROM audit_issues ai
                JOIN audits a ON ai.audit_id = a.id
                JOIN leads l ON a.lead_id = l.id
                WHERE ai.issue_type = ?
                ORDER BY ai.severity DESC
            """, (issue_type,))
            
            issues = []
            for row in cursor.fetchall():
                issues.append({
                    "lead_id": row[0],
                    "business_name": row[1],
                    "website": row[2],
                    "description": row[3],
                    "severity": row[4]
                })
        
        return issues
