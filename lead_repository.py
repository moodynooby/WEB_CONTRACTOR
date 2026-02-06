"""Simplified Lead Repository for Web Contractor TUI"""
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime


class LeadRepository:
    """Centralized database operations"""

    def __init__(self, db_path="leads.db"):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def setup_database(self):
        """Initialize database schema"""
        conn = self._get_connection()
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
            bucket TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            FOREIGN KEY(lead_id) REFERENCES leads(id)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            subject TEXT,
            body TEXT,
            status TEXT DEFAULT 'pending',
            sent_at TEXT,
            FOREIGN KEY(lead_id) REFERENCES leads(id)
        )
        """)

        # New tables for configuration
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS buckets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            categories TEXT,  -- JSON list
            search_patterns TEXT,  -- JSON list
            geographic_segments TEXT,  -- JSON list
            intent_profile TEXT,
            conversion_probability REAL,
            monthly_target INTEGER
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_name TEXT,
            issue_type TEXT,
            template_id TEXT,
            subject_pattern TEXT,
            body_template TEXT,
            tone TEXT,
            word_count_range TEXT, -- JSON list
            conversion_focus TEXT,
            UNIQUE(bucket_name, issue_type)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT -- JSON value
        )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_qualified ON audits(qualified)")
        
        conn.commit()
        conn.close()

    def save_bucket(self, bucket_data: Dict):
        """Save or update a bucket configuration"""
        conn = self._get_connection()
        cursor = conn.cursor()
        import json
        
        try:
            cursor.execute("""
                INSERT INTO buckets (name, categories, search_patterns, geographic_segments, 
                                   intent_profile, conversion_probability, monthly_target)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    categories=excluded.categories,
                    search_patterns=excluded.search_patterns,
                    geographic_segments=excluded.geographic_segments,
                    intent_profile=excluded.intent_profile,
                    conversion_probability=excluded.conversion_probability,
                    monthly_target=excluded.monthly_target
            """, (
                bucket_data["name"],
                json.dumps(bucket_data.get("categories", [])),
                json.dumps(bucket_data.get("search_patterns", [])),
                json.dumps(bucket_data.get("geographic_segments", [])),
                bucket_data.get("intent_profile", ""),
                bucket_data.get("conversion_probability", 0.0),
                bucket_data.get("monthly_target", 0)
            ))
            conn.commit()
        finally:
            conn.close()

    def get_all_buckets(self) -> List[Dict]:
        """Get all configured buckets"""
        conn = self._get_connection()
        cursor = conn.cursor()
        import json
        
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
            
        conn.close()
        return buckets

    def save_template(self, bucket_name: str, issue_type: str, template_data: Dict):
        """Save email template"""
        conn = self._get_connection()
        cursor = conn.cursor()
        import json
        
        try:
            cursor.execute("""
                INSERT INTO email_templates (bucket_name, issue_type, template_id, subject_pattern, 
                                           body_template, tone, word_count_range, conversion_focus)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket_name, issue_type) DO UPDATE SET
                    template_id=excluded.template_id,
                    subject_pattern=excluded.subject_pattern,
                    body_template=excluded.body_template,
                    tone=excluded.tone,
                    word_count_range=excluded.word_count_range,
                    conversion_focus=excluded.conversion_focus
            """, (
                bucket_name,
                issue_type,
                template_data.get("template_id"),
                template_data.get("subject_pattern"),
                template_data.get("body_template"),
                template_data.get("tone"),
                json.dumps(template_data.get("word_count_range", [])),
                template_data.get("conversion_focus")
            ))
            conn.commit()
        finally:
            conn.close()

    def get_templates_for_bucket(self, bucket_name: str) -> Dict:
        """Get all templates for a bucket"""
        conn = self._get_connection()
        cursor = conn.cursor()
        import json
        
        cursor.execute("SELECT * FROM email_templates WHERE bucket_name = ?", (bucket_name,))
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
            
        conn.close()
        return templates

    def save_config(self, key: str, value: Dict):
        """Save global config"""
        conn = self._get_connection()
        cursor = conn.cursor()
        import json
        
        try:
            cursor.execute("""
                INSERT INTO app_config (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (key, json.dumps(value)))
            conn.commit()
        finally:
            conn.close()

    def get_config(self, key: str) -> Optional[Dict]:
        """Get global config"""
        conn = self._get_connection()
        cursor = conn.cursor()
        import json
        
        cursor.execute("SELECT value FROM app_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            try:
                return json.loads(row[0])
            except:
                return None
        return None

    def save_lead(self, lead: Dict) -> int:
        """Save a single lead"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO leads (business_name, category, location, phone, email, 
                                   website, source, bucket, quality_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead.get("business_name"),
                lead.get("category"),
                lead.get("location"),
                lead.get("phone"),
                lead.get("email"),
                lead.get("website"),
                lead.get("source"),
                lead.get("bucket"),
                lead.get("quality_score", 0.5)
            ))
            lead_id = cursor.lastrowid
            conn.commit()
            return lead_id
        except sqlite3.IntegrityError:
            return -1
        finally:
            conn.close()

    def get_pending_audits(self, limit: int = 50) -> List[Dict]:
        """Get leads pending audit"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, business_name, website, bucket
            FROM leads
            WHERE status = 'pending_audit' AND website IS NOT NULL
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
        conn.close()
        return leads

    def save_audit(self, lead_id: int, audit_data: Dict):
        """Save audit results"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        import json
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
        
        # Update lead status
        new_status = "qualified" if audit_data.get("qualified") else "unqualified"
        cursor.execute("""
            UPDATE leads SET status = ? WHERE id = ?
        """, (new_status, lead_id))
        
        conn.commit()
        conn.close()

    def get_qualified_leads(self, limit: int = 50) -> List[Dict]:
        """Get qualified leads without emails"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.id, l.business_name, l.website, l.bucket, a.issues_json
            FROM leads l
            JOIN audits a ON l.id = a.lead_id
            WHERE l.status = 'qualified'
            AND NOT EXISTS (
                SELECT 1 FROM email_campaigns ec WHERE ec.lead_id = l.id
            )
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
        conn.close()
        return leads

    def save_email(self, lead_id: int, subject: str, body: str):
        """Save generated email"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO email_campaigns (lead_id, subject, body)
            VALUES (?, ?, ?)
        """, (lead_id, subject, body))
        conn.commit()
        conn.close()

    def get_pending_emails(self, limit: int = 20) -> List[Dict]:
        """Get pending emails to send"""
        conn = self._get_connection()
        cursor = conn.cursor()
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
        conn.close()
        return emails

    def mark_email_sent(self, campaign_id: int, success: bool, error: str = None):
        """Mark email as sent or failed"""
        conn = self._get_connection()
        cursor = conn.cursor()
        status = "sent" if success else "failed"
        cursor.execute("""
            UPDATE email_campaigns 
            SET status = ?, sent_at = ?
            WHERE id = ?
        """, (status, datetime.now().isoformat() if success else None, campaign_id))
        conn.commit()
        conn.close()

    def get_stats(self) -> Dict:
        """Get overall statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM leads")
        total_leads = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'qualified'")
        qualified = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM email_campaigns WHERE status = 'sent'")
        emails_sent = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM email_campaigns WHERE status = 'pending'")
        emails_pending = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_leads": total_leads,
            "qualified_leads": qualified,
            "emails_sent": emails_sent,
            "emails_pending": emails_pending
        }

    def consolidate_database(self) -> Dict:
        """Clean up and optimize database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. Remove leads with absolutely no contact info
        cursor.execute("""
            DELETE FROM leads 
            WHERE (website IS NULL OR website = '') 
            AND (phone IS NULL OR phone = '') 
            AND (email IS NULL OR email = '')
        """)
        deleted_count = cursor.rowcount
        
        # 2. Optimize database
        cursor.execute("VACUUM")
        
        conn.commit()
        conn.close()
        
        return {
            "deleted_empty_leads": deleted_count,
            "status": "optimized"
        }
