import sqlite3

def init_database():
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    # Leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT NOT NULL,
        category TEXT,
        location TEXT,
        phone TEXT,
        email TEXT,
        website TEXT UNIQUE,
        source TEXT,
        status TEXT DEFAULT 'pending_audit'
    )
    ''')

    # Audit results
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        url TEXT,
        score INTEGER,
        priority TEXT,
        issues_json TEXT,
        qualified INTEGER DEFAULT 0,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )
    ''')

    # Email campaigns
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS email_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        subject TEXT,
        body TEXT,
        status TEXT DEFAULT 'pending',
        sent_at TEXT,
        replied INTEGER DEFAULT 0,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )
    ''')

    conn.commit()
    conn.close()
    print("✓ Database created: leads.db")

if __name__ == '__main__':
    init_database()
