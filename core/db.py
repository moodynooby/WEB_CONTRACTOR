import sqlite3
import json
from datetime import datetime

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
        estimated_fix_cost TEXT,
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

    # Create indexes for better performance (only for existing columns)
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
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()
    
    stats = {}
    
    # Total leads
    cursor.execute('SELECT COUNT(*) FROM leads')
    stats['total_leads'] = cursor.fetchone()[0]
    
    # Total leads by status
    cursor.execute('''
    SELECT status, COUNT(*) FROM leads GROUP BY status
    ''')
    stats['leads_by_status'] = dict(cursor.fetchall())
    
    # Leads by source
    cursor.execute('''
    SELECT source, COUNT(*) FROM leads GROUP BY source
    ''')
    stats['leads_by_source'] = dict(cursor.fetchall())
    
    # Leads by bucket
    cursor.execute('''
    SELECT bucket, COUNT(*) FROM leads WHERE bucket IS NOT NULL GROUP BY bucket
    ''')
    stats['leads_by_bucket'] = dict(cursor.fetchall())
    
    # Audit statistics
    cursor.execute('SELECT COUNT(*) FROM audits')
    stats['total_audits'] = cursor.fetchone()[0]
    
    cursor.execute('''
    SELECT qualified, COUNT(*) FROM audits GROUP BY qualified
    ''')
    stats['audits_by_qualified'] = dict(cursor.fetchall())
    
    # Campaign statistics
    cursor.execute('SELECT COUNT(*) FROM email_campaigns')
    stats['total_emails'] = cursor.fetchone()[0]
    
    cursor.execute('''
    SELECT status, COUNT(*) FROM email_campaigns GROUP BY status
    ''')
    stats['emails_by_status'] = dict(cursor.fetchall())
    
    # Quality metrics
    cursor.execute('SELECT AVG(personalization_score) FROM email_campaigns WHERE personalization_score IS NOT NULL')
    avg_pers = cursor.fetchone()[0]
    stats['avg_personalization_score'] = avg_pers if avg_pers else 0.0
    
    cursor.execute('SELECT AVG(overall_score) FROM audits WHERE overall_score IS NOT NULL')
    avg_audit_score = cursor.fetchone()[0]
    stats['avg_audit_score'] = avg_audit_score if avg_audit_score else 0.0
    
    conn.close()
    return stats

def log_scraping_session(source: str, query: str, leads_found: int, leads_saved: int, error_message: str = None):
    """Log scraping session for analytics"""
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO scraping_logs 
    (source, query, leads_found, leads_saved, error_message)
    VALUES (?, ?, ?, ?, ?)
    ''', (source, query, leads_found, leads_saved, error_message))
    
    conn.commit()
    conn.close()

def record_analytic(metric_name: str, metric_value: float, bucket: str = None, source: str = None, notes: str = None):
    """Record analytics data"""
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO analytics 
    (metric_name, metric_value, bucket, source, date_recorded, notes)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (metric_name, metric_value, bucket, source, datetime.now().date(), notes))
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_database()
    populate_buckets()
    
    # Show database stats
    stats = get_database_stats()
    print("\n=== DATABASE STATISTICS ===")
    for category, data in stats.items():
        print(f"\n{category.replace('_', ' ').title()}:")
        for key, value in data.items():
            print(f"  {key}: {value}")
