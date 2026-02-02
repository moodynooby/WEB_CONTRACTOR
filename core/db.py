import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any

# Keep standalone functions for setup/stats
def init_database():
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    # Leads table with enhanced fields
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT NOT NULL,
        category TEXT,
        location TEXT,
        city TEXT,
        phone TEXT,
        email TEXT,
        website TEXT UNIQUE,
        source TEXT,
        status TEXT DEFAULT 'pending_audit',
        quality_score REAL DEFAULT 0.5,
        bucket TEXT,
        tier TEXT,
        priority INTEGER DEFAULT 3,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Enhanced audit results with new fields for Stage B
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        url TEXT,
        score INTEGER,
        priority TEXT,
        issues_json TEXT,
        qualified INTEGER DEFAULT 0,
        overall_score REAL DEFAULT 0.0,
        technical_metrics TEXT,  -- JSON for detailed metrics
        audit_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )
    ''')

    # Enhanced email campaigns with Stage C fields
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS email_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        subject TEXT,
        body TEXT,
        status TEXT DEFAULT 'pending',
        sent_at TEXT,
        replied INTEGER DEFAULT 0,
        opened INTEGER DEFAULT 0,
        clicked INTEGER DEFAULT 0,
        campaign_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tone TEXT,  -- professional, friendly, urgent, casual
        word_count INTEGER,
        personalization_score REAL DEFAULT 0.0,
        urgency_level TEXT,  -- high, medium, low
        call_to_action TEXT,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )
    ''')

    # New table for lead buckets
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lead_buckets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bucket_name TEXT UNIQUE NOT NULL,
        categories TEXT,  -- JSON array
        geographic_focus TEXT,  -- JSON array
        conversion_probability REAL,
        monthly_target INTEGER,
        active INTEGER DEFAULT 1
    )
    ''')

    # New table for scraping logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scraping_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        query TEXT,
        leads_found INTEGER DEFAULT 0,
        leads_saved INTEGER DEFAULT 0,
        error_message TEXT,
        scrape_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # New table for analytics
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        bucket TEXT,
        source TEXT,
        date_recorded DATE,
        notes TEXT
    )
    ''')
    
    # Indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audits_qualified ON audits(qualified)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_campaigns_status ON email_campaigns(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scraping_logs_date ON scraping_logs(scrape_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_analytics_date ON analytics(date_recorded)')

    conn.commit()
    conn.close()
    print("✓ Enhanced database created: leads.db")

def populate_buckets():
    """Populate lead buckets table with initial data"""
    from core.lead_buckets import LeadBucketManager
    
    manager = LeadBucketManager()
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()
    
    for bucket in manager.buckets:
        cursor.execute('''
        INSERT OR REPLACE INTO lead_buckets 
        (bucket_name, categories, geographic_focus, conversion_probability, monthly_target)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            bucket.name,
            json.dumps(bucket.categories),
            json.dumps([seg.tier for seg in bucket.geographic_segments]),
            bucket.conversion_probability,
            bucket.monthly_target
        ))
    
    conn.commit()
    conn.close()
    print("✓ Lead buckets populated")

def get_database_stats():
    """Get database statistics"""
    repo = LeadRepository()
    return repo.get_stats()

def log_scraping_session(source: str, query: str, leads_found: int, leads_saved: int, error_message: str = None):
    """Log scraping session for analytics"""
    repo = LeadRepository()
    repo.log_scraping_session(source, query, leads_found, leads_saved, error_message)

def record_analytic(metric_name: str, metric_value: float, bucket: str = None, source: str = None, notes: str = None):
    """Record analytics data"""
    repo = LeadRepository()
    repo.record_analytic(metric_name, metric_value, bucket, source, notes)

class LeadRepository:
    """Centralized Data Access Layer for Lead Management System"""
    
    def __init__(self, db_path='leads.db'):
        self.db_path = db_path

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Lead Operations ---
    def add_lead(self, lead_data: Dict) -> bool:
        """Add a single lead to the database. Returns True if new/updated, False if error."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR REPLACE INTO leads 
            (business_name, category, location, phone, email, website, source, status, quality_score, bucket)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lead_data.get('business_name'),
                lead_data.get('category', 'Unknown'),
                lead_data.get('location'),
                lead_data.get('phone'),
                lead_data.get('email'),
                lead_data.get('website'),
                lead_data.get('source'),
                lead_data.get('status', 'pending_audit'),
                lead_data.get('quality_score', 0.5),
                lead_data.get('bucket')
            ))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"DB Error adding lead: {e}")
            return False

    def add_leads_bulk(self, leads: List[Dict]) -> int:
        """Add multiple leads. Returns count of successfully saved leads."""
        saved_count = 0
        conn = self._get_connection()
        cursor = conn.cursor()
                
        for lead in leads:
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO leads 
                (business_name, category, location, phone, email, website, source, status, quality_score, bucket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lead.get('business_name'),
                    lead.get('category', 'Unknown'),
                    lead.get('location'),
                    lead.get('phone'),
                    lead.get('email'),
                    lead.get('website'),
                    lead.get('source'),
                    lead.get('status', 'pending_audit'),
                    lead.get('quality_score', 0.5),
                    lead.get('bucket')
                ))
                saved_count += 1
            except Exception as e:
                print(f"Error saving lead {lead.get('business_name')}: {e}")
        
        conn.commit()
        conn.close()
        return saved_count

    def update_lead(self, lead_id: int, **kwargs) -> bool:
        """Update specific fields of a lead"""
        if not kwargs:
            return False
            
        set_clauses = []
        values = []
        
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)
            
        values.append(lead_id)
        
        query = f"UPDATE leads SET {', '.join(set_clauses)} WHERE id = ?"
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query, values)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating lead {lead_id}: {e}")
            return False

    # --- Audit Operations ---
    def get_pending_audits(self, limit: int = 10) -> List[Dict]:
        """Get leads pending audit"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, website, business_name, category 
        FROM leads 
        WHERE status = 'pending_audit' AND website IS NOT NULL 
        LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        
        # Mark as processing
        for row in rows:
            cursor.execute('UPDATE leads SET status = "auditing" WHERE id = ?', (row['id'],))
        
        conn.commit()
        
        results = [dict(row) for row in rows]
        conn.close()
        return results

    def save_audit_result(self, lead_id: int, result_data: Dict):
        """Save audit result and update lead status"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT OR REPLACE INTO audits
        (lead_id, overall_score, issues_json, technical_metrics, qualified, audit_date, llm_analysis)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            lead_id,
            result_data.get('overall_score'),
            json.dumps(result_data.get('issues', [])),
            json.dumps(result_data.get('technical_metrics', {})),
            result_data.get('qualified', 0),
            datetime.now().isoformat(),
            json.dumps(result_data.get('llm_analysis', {}))
        ))
        
        status = 'qualified' if result_data.get('qualified') else 'disqualified'
        cursor.execute('UPDATE leads SET status = ? WHERE id = ?', (status, lead_id))
        
        conn.commit()
        conn.close()

    # --- Campaign Operations ---
    def get_qualified_leads_for_email(self, limit: int = 50) -> List[Dict]:
        """Get qualified leads that don't have an email campaign yet"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT l.id, l.business_name, l.bucket, a.issues_json, a.overall_score, a.llm_analysis
        FROM leads l
        JOIN audits a ON l.id = a.lead_id
        WHERE a.qualified = 1 
        AND l.id NOT IN (
            SELECT DISTINCT lead_id FROM email_campaigns
        )
        ORDER BY a.overall_score DESC
        LIMIT ?
        ''', (limit,))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def save_email_campaign(self, campaign_data: Dict):
        """Save generated email campaign"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO email_campaigns 
        (lead_id, subject, body, status, tone, word_count, personalization_score, urgency_level, call_to_action)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            campaign_data['lead_id'],
            campaign_data['subject'],
            campaign_data['body'],
            campaign_data.get('status', 'pending'),
            campaign_data.get('tone'),
            campaign_data.get('word_count'),
            campaign_data.get('personalization_score'),
            campaign_data.get('urgency_level'),
            campaign_data.get('call_to_action')
        ))
        
        conn.commit()
        conn.close()

    # --- Analytics & Stats ---
    def get_stats(self) -> Dict:
        """Get comprehensive database stats"""
        conn = self._get_connection()
        cursor = conn.cursor()
        stats = {}
        
        # Simple counts
        stats['total_leads'] = cursor.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
        stats['total_audits'] = cursor.execute('SELECT COUNT(*) FROM audits').fetchone()[0]
        stats['total_emails'] = cursor.execute('SELECT COUNT(*) FROM email_campaigns').fetchone()[0]
        
        # Grouped stats
        stats['leads_by_status'] = dict(cursor.execute('SELECT status, COUNT(*) FROM leads GROUP BY status').fetchall())
        stats['leads_by_source'] = dict(cursor.execute('SELECT source, COUNT(*) FROM leads GROUP BY source').fetchall())
        stats['leads_by_bucket'] = dict(cursor.execute('SELECT bucket, COUNT(*) FROM leads WHERE bucket IS NOT NULL GROUP BY bucket').fetchall())
        stats['audits_by_qualified'] = dict(cursor.execute('SELECT qualified, COUNT(*) FROM audits GROUP BY qualified').fetchall())
        stats['emails_by_status'] = dict(cursor.execute('SELECT status, COUNT(*) FROM email_campaigns GROUP BY status').fetchall())
        
        # Averages
        avg_pers = cursor.execute('SELECT AVG(personalization_score) FROM email_campaigns WHERE personalization_score IS NOT NULL').fetchone()[0]
        stats['avg_personalization_score'] = avg_pers if avg_pers else 0.0
        
        avg_audit = cursor.execute('SELECT AVG(overall_score) FROM audits WHERE overall_score IS NOT NULL').fetchone()[0]
        stats['avg_audit_score'] = avg_audit if avg_audit else 0.0
        
        conn.close()
        return stats

    def log_scraping_session(self, source: str, query: str, leads_found: int, leads_saved: int, error_message: str = None):
        """Log scraping session"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO scraping_logs (source, query, leads_found, leads_saved, error_message)
        VALUES (?, ?, ?, ?, ?)
        ''', (source, query, leads_found, leads_saved, error_message))
        conn.commit()
        conn.close()

    def record_analytic(self, metric_name: str, metric_value: float, bucket: str = None, source: str = None, notes: str = None):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO analytics (metric_name, metric_value, bucket, source, date_recorded, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (metric_name, metric_value, bucket, source, datetime.now().date(), notes))
        conn.commit()
        conn.close()

    def get_monthly_stats(self, month_prefix: str) -> Dict:
        """Get statistics for a specific month (e.g. '2023-10')"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Monthly total
        cursor.execute("SELECT COUNT(*) FROM leads WHERE created_at LIKE ?", (f"{month_prefix}%",))
        monthly_total = cursor.fetchone()[0]
        
        # By source
        cursor.execute("SELECT source, COUNT(*) FROM leads WHERE created_at LIKE ? GROUP BY source", (f"{month_prefix}%",))
        by_source = dict(cursor.fetchall())
        
        # By bucket
        cursor.execute("SELECT bucket, COUNT(*) FROM leads WHERE created_at LIKE ? GROUP BY bucket", (f"{month_prefix}%",))
        by_bucket = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'monthly_total': monthly_total,
            'by_source': by_source,
            'by_bucket': by_bucket
        }

    def get_leads(self, page: int = 1, per_page: int = 20, status: str = None, bucket: str = None) -> Dict:
        """Get paginated leads with filters"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        where_clause = "WHERE 1=1"
        params = []
        
        if status:
            where_clause += " AND status = ?"
            params.append(status)
        
        if bucket:
            where_clause += " AND bucket = ?"
            params.append(bucket)
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM leads {where_clause}"
        total = cursor.execute(count_query, params).fetchone()[0]
        
        # Get paginated results
        offset = (page - 1) * per_page
        query = f'''
            SELECT business_name, category, location, website, status, quality_score, bucket, source
            FROM leads
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        '''
        leads = cursor.execute(query, params + [per_page, offset]).fetchall()
        conn.close()
        
        return {
            'leads': [dict(ix) for ix in leads],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        }

    def get_scraping_logs(self, days: int = 7) -> List[Dict]:
        """Get scraping logs for recent days"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT source, DATE(scrape_date) as date, 
                   SUM(leads_found) as found, 
                   SUM(leads_saved) as saved
            FROM scraping_logs 
            WHERE scrape_date >= date('now', '-{days} days')
            GROUP BY source, DATE(scrape_date)
            ORDER BY date DESC
        ''')
        data = [dict(ix) for ix in cursor.fetchall()]
        conn.close()
        return data

    def get_recent_analytics(self, days: int = 30) -> List[Dict]:
        """Get recent analytics metrics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT metric_name, metric_value, source, date_recorded
            FROM analytics 
            WHERE date_recorded >= date('now', '-{days} days')
            ORDER BY date_recorded DESC
        ''')
        data = [dict(ix) for ix in cursor.fetchall()]
        conn.close()
        return data

    def get_email_campaign(self, campaign_id: int) -> Optional[Dict]:
        """Get email campaign details with lead info"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT l.email, l.business_name, l.id as lead_id, ec.subject, ec.body 
            FROM email_campaigns ec 
            JOIN leads l ON ec.lead_id = l.id 
            WHERE ec.id = ?
        ''', (campaign_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reviewable_emails(self, min_score: float = 0.7) -> List[Dict]:
        """Fetch pending emails for high-quality leads"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                ec.id as campaign_id,
                l.id as lead_id,
                l.business_name,
                l.website,
                l.email as lead_email,
                a.overall_score,
                a.llm_analysis,
                ec.subject,
                ec.body,
                l.bucket
            FROM email_campaigns ec
            JOIN leads l ON ec.lead_id = l.id
            JOIN audits a ON l.id = a.lead_id
            WHERE ec.status = 'pending'
            AND a.overall_score >= ?
            AND a.qualified = 1
            ORDER BY a.overall_score DESC
        ''', (min_score,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_campaign_status(self, campaign_id: int, status: str, body: Optional[str] = None, error_message: Optional[str] = None):
        """Update campaign status with enhanced metadata"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        if status == 'sent':
            cursor.execute('''
                UPDATE email_campaigns 
                SET status = ?, body = ?, sent_at = ?, error_log = NULL
                WHERE id = ?
            ''', (status, body, now, campaign_id))
        elif status == 'failed':
            cursor.execute('''
                UPDATE email_campaigns 
                SET status = ?, error_log = ?
                WHERE id = ?
            ''', (status, error_message, campaign_id))
        elif status == 'ignored':
            cursor.execute('UPDATE email_campaigns SET status = ? WHERE id = ?', (status, campaign_id))
            # Reject lead
            cursor.execute('''
                UPDATE leads SET status = 'rejected'
                WHERE id = (SELECT lead_id FROM email_campaigns WHERE id = ?)
            ''', (campaign_id,))
        else:
            cursor.execute('UPDATE email_campaigns SET status = ? WHERE id = ?', (status, campaign_id))
            
        conn.commit()
        conn.close()

    def get_pending_emails_to_send(self, limit: int = 50) -> List[Dict]:
        """Get approved emails ready to send"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ec.id, ec.lead_id, ec.subject, ec.body, l.business_name
            FROM email_campaigns ec
            JOIN leads l ON ec.lead_id = l.id
            WHERE ec.status = 'approved'
            ORDER BY ec.campaign_date ASC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_lead_email(self, lead_id: int) -> Optional[str]:
        """Get email address for a lead"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT email FROM leads WHERE id = ?', (lead_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    def get_audit_statistics(self) -> Dict:
        """Get overall audit statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get audit stats
        cursor.execute('''
        SELECT 
            COUNT(*) as total_audits,
            COUNT(CASE WHEN qualified = 1 THEN 1 END) as qualified,
            AVG(overall_score) as avg_score,
            COUNT(*) as total
        FROM audits
        ''')
        
        audit_stats = cursor.fetchone()
        
        # Get issue statistics
        cursor.execute('SELECT issues_json FROM audits WHERE issues_json IS NOT NULL')
        all_issues_json = cursor.fetchall()
        
        issue_counts = {}
        for (issues_json,) in all_issues_json:
            try:
                issues = json.loads(issues_json)
                for issue in issues:
                    issue_type = issue.get('issue_type', 'unknown')
                    issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
            except:
                continue
        
        conn.close()
        
        return {
            'total_audits': audit_stats[0] or 0,
            'qualified_count': audit_stats[1] or 0,
            'qualification_rate': (audit_stats[1] or 0) / max(audit_stats[0] or 1, 1),
            'average_score': audit_stats[2] or 0,
            'top_issues': dict(sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        }

    def get_email_statistics(self) -> Dict:
        """Get email generation statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 
            COUNT(*) as total_emails,
            COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
            AVG(personalization_score) as avg_personalization,
            AVG(word_count) as avg_word_count
        FROM email_campaigns
        ''')
        
        stats = cursor.fetchone()
        conn.close()
        
        return {
            'total_generated': stats[0] or 0,
            'sent': stats[1] or 0,
            'pending': stats[2] or 0,
            'failed': stats[3] or 0,
            'personalization_avg': stats[4] or 0,
            'word_count_avg': stats[5] or 0
        }

if __name__ == '__main__':
    # Initialize DB if run directly
    init_database()
    populate_buckets()
    print("Database Initialized")
